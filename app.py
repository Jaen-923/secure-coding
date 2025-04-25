import sqlite3
import bcrypt
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from flask_socketio import SocketIO, send
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일에서 환경 변수 로드

app = Flask(__name__)

CORS(app, resources={r"/api/*": {
    "origins": "http://localhost:5000",
    "methods": ["GET", "POST", "PUT", "DELETE"],  
}})

app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
DATABASE = 'market.db'
socketio = SocketIO(app)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# 테이블 생성 (최초 실행 시에만)
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # users 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                nickname VARCHAR(255) NOT NULL UNIQUE,
                bio TEXT,
                role VARCHAR(50) NOT NULL,
                is_banned BOOLEAN DEFAULT FALSE,
                created_at DATETIME
            )
        """)

        # products 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255),
                description TEXT,
                price INT,
                status VARCHAR(20) DEFAULT '판매중',
                seller_id VARCHAR(36),
                created_at DATETIME,
                FOREIGN KEY (seller_id) REFERENCES users(id)
            )
        """)

        # item_likes 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_likes (
                user_id VARCHAR(36),
                item_id VARCHAR(36),
                liked_at DATETIME,
                PRIMARY KEY (user_id, item_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (item_id) REFERENCES products(id)
            )
        """)

        # point_transactions 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS point_transactions (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36),
                type VARCHAR(50),
                amount INT,
                target_id VARCHAR(36),
                item_id VARCHAR(36),
                created_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (target_id) REFERENCES users(id),
                FOREIGN KEY (item_id) REFERENCES products(id)
            )
        """)

        # reports 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id VARCHAR(36) PRIMARY KEY,
                reporter_id VARCHAR(36),
                target_id VARCHAR(36),
                type VARCHAR(20),
                reason TEXT,
                created_at DATETIME,
                FOREIGN KEY (reporter_id) REFERENCES users(id)
            )
        """)

        db.commit()

@app.before_request
def before_request():
    if 'user_id' not in session and request.endpoint not in ['login_page', 'register_page', 'login', 'signup', 'static']:
        return redirect(url_for('login_page'))



# 기본 라우트
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/home')
def dashboard():
    return render_template('home.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/mypage')
def mypage():
    return render_template('mypage.html')

@app.route('/product/register')
def product_register_page():
    return render_template('register-product.html')

@app.route('/point')
def point_charge_page():
    return render_template('charge-points.html')

@app.route('/change/password')
def change_password_page():
    return render_template('change-password.html')

@app.route('/product/<item_id>')
def product_detail_page(item_id):
    return render_template('view_product.html', item_id=item_id)

@app.route('/items/<item_id>', methods=['GET'])
def get_item_detail(item_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            p.*, 
            u.nickname as seller_nickname,
            (SELECT COUNT(*) FROM item_likes WHERE item_id = p.id) AS like_count
        FROM products p
        JOIN users u ON p.seller_id = u.id
        WHERE p.id = ?
    """, (item_id,))
    item = cursor.fetchone()
    if not item:
        return jsonify({'message': '상품을 찾을 수 없습니다.'}), 404
    return jsonify(dict(item))



@app.route('/product/new', methods=['POST'])
def create_product():
    if 'user_id' not in session:
        return jsonify({'message': '로그인이 필요합니다.'}), 401

    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    price = data.get('price')

    if not title or not description or not price:
        return jsonify({'message': '모든 항목을 입력해주세요.'}), 400

    try:
        product_id = str(uuid.uuid4())
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO products (id, title, description, price, status, seller_id, created_at)
            VALUES (?, ?, ?, ?, '판매중', ?, ?)
        """, (product_id, title, description, int(price), session['user_id'], datetime.utcnow()))
        db.commit()
        return jsonify({'message': '상품이 등록되었습니다.'})
    except Exception as e:
        return jsonify({'message': '상품 등록 실패', 'error': str(e)}), 500


# 로그인
@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
        session['user_id'] = user['id']
        return jsonify({'message': '로그인 성공'})
    else:
        return jsonify({'message': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 401


# --- 로그아웃 ---
@app.route('/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': '로그아웃 되었습니다.'})

# --- 회원가입 ---
# 회원가입
@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    nickname = data.get('nickname')
    bio = data.get('bio', '')
    user_id = str(uuid.uuid4())
    
    # 비밀번호 해싱
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (id, username, password, nickname, bio, role, created_at) 
            VALUES (?, ?, ?, ?, ?, 'user', ?)
        """, (user_id, username, hashed_password, nickname, bio, datetime.utcnow()))
        db.commit()
        return jsonify({'message': '회원가입 성공'})
    except sqlite3.IntegrityError:
        return jsonify({'message': '이미 존재하는 사용자입니다.'}), 409

    
# --- 비밀번호 변경 ---
# 비밀번호 변경
@app.route('/auth/pwchange', methods=['PATCH'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'message': '로그인이 필요합니다.'}), 401

    data = request.get_json()
    current_pw = data.get('current_password')
    new_pw = data.get('new_password')

    db = get_db()
    cursor = db.cursor()
    
    # 현재 비밀번호 확인
    cursor.execute("SELECT password FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()

    if not user or not bcrypt.checkpw(current_pw.encode('utf-8'), user['password'].encode('utf-8')):
        return jsonify({'message': '현재 비밀번호가 일치하지 않습니다.'}), 403

    try:
        # 새로운 비밀번호 해시 처리
        hashed_new_pw = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt())

        # 비밀번호 업데이트
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_new_pw, session['user_id']))
        db.commit()
        
        return jsonify({'message': '비밀번호가 변경되었습니다.'})

    except Exception as e:
        return jsonify({'message': '비밀번호 변경 실패', 'error': str(e)}), 500



# --- 비밀번호 찾기 ---
@app.route('/auth/pwfind', methods=['POST'])
def find_password():
    data = request.get_json()
    username = data.get('username')
    new_pw = data.get('new_password')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({'message': '존재하지 않는 사용자입니다.'}), 404

    cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_pw, username))
    db.commit()
    return jsonify({'message': '비밀번호가 초기화되었습니다. 로그인 후 변경해주세요.'})


# --- 마이페이지 조회 ---
@app.route('/users/myProfile', methods=['GET'])
def my_profile():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()

    # 사용자 기본 정보
    cursor.execute("SELECT id, username, nickname, bio, role FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()
    if not user:
        return jsonify({'message': '유저 정보를 찾을 수 없습니다.'}), 404

    # 포인트 총합
    cursor.execute("SELECT COALESCE(SUM(CASE WHEN type='충전' THEN amount WHEN type='출금' OR type='구매' THEN -amount ELSE 0 END), 0) as points FROM point_transactions WHERE user_id = ?", (session['user_id'],))
    points = cursor.fetchone()['points']

    user_info = dict(user)
    user_info['points'] = points

    return jsonify(user_info)


# --- 소개글 변경 ---
@app.route('/users/myProfile/intro', methods=['PATCH'])
def update_intro():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    intro = request.json.get('intro', '')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET bio = ? WHERE id = ?", (intro, session['user_id']))
    db.commit()
    return jsonify({'message': '소개글이 변경되었습니다.'})

# --- 닉네임 변경 ---
@app.route('/users/myProfile/nickname', methods=['PATCH'])
def update_nickname():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    nickname = request.json.get('nickname')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET username = ? WHERE id = ?", (nickname, session['user_id']))
    db.commit()
    return jsonify({'message': '닉네임이 변경되었습니다.'})

# --- 회원탈퇴 ---
@app.route('/auth/delete', methods=['DELETE'])
def delete_account():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (session['user_id'],))
    db.commit()
    session.pop('user_id', None)
    return jsonify({'message': '회원탈퇴 완료'})

# --- 악성 유저 신고 ---
@app.route('/users/report', methods=['POST'])
def report_user():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    data = request.get_json()
    target_id = data.get('target_id')
    reason = data.get('reason')
    report_type = data.get('type')  # 'user' or 'item'

    if report_type not in ['user', 'item']:
        return jsonify({'message': '신고 유형은 user 또는 item 중 하나여야 합니다.'}), 400

    # 이미 신고한 상품인지 체크
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT * FROM reports WHERE reporter_id = ? AND target_id = ? AND type = ?
    """, (session['user_id'], target_id, report_type))
    existing_report = cursor.fetchone()

    if existing_report:
        return jsonify({'message': '이미 신고한 상품입니다.'}), 409

    # 신고 데이터 삽입
    report_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO reports (id, reporter_id, target_id, type, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (report_id, session['user_id'], target_id, report_type, reason, datetime.utcnow()))
    db.commit()

    return jsonify({'message': '신고가 접수되었습니다.'})


# --- 상품 상태 변경 (판매중 <-> 거래완료) ---
@app.route('/items/<item_id>/status', methods=['PATCH'])
def change_item_status(item_id):
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    new_status = request.json.get('status')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE products SET status = ? WHERE id = ?", (new_status, item_id))
    db.commit()
    return jsonify({'message': '상품 상태가 변경되었습니다.'})

# --- 내가 등록한 상품 조회 ---
@app.route('/items/myItems', methods=['GET'])
def get_my_items():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            p.*,
            (SELECT COUNT(*) FROM item_likes WHERE item_id = p.id) AS like_count,
            EXISTS (
                SELECT 1 FROM item_likes 
                WHERE item_id = p.id AND user_id = ?
            ) AS liked_by_me
        FROM products p
        WHERE seller_id = ? AND p.status = '판매중'
    """, (session['user_id'], session['user_id']))
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify(items)

# --- 포인트 충전 ---
@app.route('/points/deposit', methods=['POST'])
def deposit_points():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    # 요청 데이터 받기
    data = request.get_json()
    amount = data.get('amount')
    password = data.get('password')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()

    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'message': '비밀번호가 일치하지 않습니다.'}), 403


    # 포인트 충전 처리
    try:
        transaction_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO point_transactions (id, user_id, type, amount, created_at)
            VALUES (?, ?, '충전', ?, ?)
        """, (transaction_id, session['user_id'], amount, datetime.utcnow()))
        
        # 포인트 충전 성공
        db.commit()
        return jsonify({'message': '포인트가 충전되었습니다.'})
    except Exception as e:
        return jsonify({'message': '포인트 충전 실패', 'error': str(e)}), 500


# --- 포인트 사용 ---
@app.route('/points/buy', methods=['POST'])
def use_points():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.get_json()
    item_id = data.get('item_id')
    amount = data.get('amount')

    db = get_db()
    cursor = db.cursor()

    # 포인트를 차감하고 상품 상태를 '거래완료'로 변경
    try:
        # 포인트 차감 처리 (예시로 단순히 포인트 차감)
        transaction_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO point_transactions (id, user_id, type, amount, item_id, created_at)
            VALUES (?, ?, '구매', ?, ?, ?)
        """, (transaction_id, session['user_id'], amount, item_id, datetime.utcnow()))
        
        # 상품 상태 변경 (판매중 -> 거래완료)
        cursor.execute("""
            UPDATE products
            SET status = '거래완료'
            WHERE id = ?
        """, (item_id,))
        
        db.commit()
        return jsonify({'message': '포인트가 사용되었습니다. 상품이 거래완료되었습니다.'})
    except Exception as e:
        return jsonify({'message': '포인트 사용 실패', 'error': str(e)}), 500



@app.route('/items/<item_id>/like', methods=['POST'])
def toggle_like(item_id):
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM item_likes WHERE user_id = ? AND item_id = ?", (session['user_id'], item_id))
    like = cursor.fetchone()

    if like:
        cursor.execute("DELETE FROM item_likes WHERE user_id = ? AND item_id = ?", (session['user_id'], item_id))
        db.commit()
        return jsonify({'message': '좋아요 취소', 'liked': False})
    else:
        cursor.execute("INSERT INTO item_likes (user_id, item_id, liked_at) VALUES (?, ?, ?)", (session['user_id'], item_id, datetime.utcnow()))
        db.commit()
        return jsonify({'message': '좋아요 추가', 'liked': True})

# --- 인기 상품 조회 (좋아요 순) ---
@app.route('/items/popular', methods=['GET'])
def get_popular_items():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            p.*, 
            (SELECT COUNT(*) FROM item_likes WHERE item_id = p.id) AS like_count,
            (SELECT COUNT(*) FROM item_likes WHERE item_id = p.id AND user_id = ?) AS liked_by_me
        FROM products p
        WHERE p.status = '판매중'
        ORDER BY like_count DESC
        LIMIT 10
    """, (session['user_id'],))
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify(items)

# --- 전체 상품 조회 (최신순) ---
@app.route('/items/all', methods=['GET'])
def get_all_items():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            p.*, 
            (SELECT COUNT(*) FROM item_likes WHERE item_id = p.id) AS like_count,
            (SELECT COUNT(*) FROM item_likes WHERE item_id = p.id AND user_id = ?) AS liked_by_me
        FROM products p
        WHERE p.status = '판매중'
        ORDER BY created_at DESC
    """, (session['user_id'],))
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify(items)




if __name__ == '__main__':
    init_db()  # DB 테이블 최초 생성용
    socketio.run(app, debug=True)  