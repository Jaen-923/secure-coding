import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from flask_socketio import SocketIO, send

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
DATABASE = 'market.db'
socketio = SocketIO(app)

# 데이터베이스 연결 관리: 요청마다 연결 생성 후 사용, 종료 시 close
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # 결과를 dict처럼 사용하기 위함
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
                nicname VARCHAR(255) NOT NULL UNIQUE
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
                status VARCHAR(20),
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


# 기본 라우트
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    if user:
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
@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    nickname = data.get('nickname')
    user_id = str(uuid.uuid4())
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO users (id, username, password, nickname, bio, role, created_at) VALUES (?, ?, ?, ?, ?, 'user', ?)",
               (user_id, username, password, nickname, bio, datetime.utcnow()))
        db.commit()
        return jsonify({'message': '회원가입 성공'})
    except:
        return jsonify({'message': '이미 존재하는 사용자입니다.'}), 409
    
# --- 비밀번호 변경 ---
@app.route('/auth/pwchange', methods=['PATCH'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'message': '로그인이 필요합니다.'}), 401

    data = request.get_json()
    current_pw = data.get('current_password')
    new_pw = data.get('new_password')

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()

    if not user or user['password'] != current_pw:
        return jsonify({'message': '현재 비밀번호가 일치하지 않습니다.'}), 403

    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_pw, session['user_id']))
    db.commit()
    return jsonify({'message': '비밀번호가 변경되었습니다.'})

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
    cursor.execute("SELECT id, username, bio, role FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()
    return jsonify(dict(user))

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

    report_id = str(uuid.uuid4())
    db = get_db()
    cursor = db.cursor()
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
    cursor.execute("SELECT * FROM products WHERE seller_id = ?", (session['user_id'],))
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify(items)

# --- 내가 좋아요한 상품 조회 ---
@app.route('/users/myProfile/likes', methods=['GET'])
def get_liked_items():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.* FROM products p
        JOIN item_likes l ON p.id = l.item_id
        WHERE l.user_id = ?
    """, (session['user_id'],))
    liked_items = [dict(row) for row in cursor.fetchall()]
    return jsonify(liked_items)

# --- 포인트 충전 ---
@app.route('/points/deposit', methods=['POST'])
def deposit_points():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    amount = request.json.get('amount')
    db = get_db()
    cursor = db.cursor()
    transaction_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO point_transactions (id, user_id, type, amount, created_at)
        VALUES (?, ?, '충전', ?, ?)
    """, (transaction_id, session['user_id'], amount, datetime.utcnow()))
    db.commit()
    return jsonify({'message': '포인트가 충전되었습니다.'})

# --- 포인트 출금 ---
@app.route('/points/withdraw', methods=['POST'])
def withdraw_points():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    amount = request.json.get('amount')
    db = get_db()
    cursor = db.cursor()
    transaction_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO point_transactions (id, user_id, type, amount, created_at)
        VALUES (?, ?, '출금', ?, ?)
    """, (transaction_id, session['user_id'], amount, datetime.utcnow()))
    db.commit()
    return jsonify({'message': '포인트가 출금되었습니다.'})

# --- 포인트 사용 ---
@app.route('/points/buy', methods=['POST'])
def use_points():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    item_id = request.json.get('item_id')
    amount = request.json.get('amount')
    db = get_db()
    cursor = db.cursor()
    transaction_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO point_transactions (id, user_id, type, amount, item_id, created_at)
        VALUES (?, ?, '구매', ?, ?, ?)
    """, (transaction_id, session['user_id'], amount, item_id, datetime.utcnow()))
    db.commit()
    return jsonify({'message': '포인트가 사용되었습니다.'})

# --- 검색 API ---
@app.route('/items/search')
def search_items():
    query = request.args.get('query', '')
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM products WHERE title LIKE ? OR description LIKE ?", 
                   (f'%{query}%', f'%{query}%'))
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)

# --- 정렬 API ---
@app.route('/items/sort')
def sort_items():
    sort_by = request.args.get('by', 'created_at')
    if sort_by not in ['created_at', 'price', 'title']:
        sort_by = 'created_at'
    db = get_db()
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM products ORDER BY {sort_by} DESC")
    results = [dict(row) for row in cursor.fetchall()]
    return jsonify(results)
