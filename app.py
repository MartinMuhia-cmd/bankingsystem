import os, sqlite3, secrets, hmac, hashlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'banking_demo.sqlite3'))

# Load a local .env file without requiring an ORM or extra dependency.
def load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env(os.path.join(BASE_DIR, '.env'))
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.execute('PRAGMA journal_mode = WAL')
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      display_name TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS accounts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      account_number TEXT NOT NULL UNIQUE,
      account_type TEXT NOT NULL DEFAULT 'Everyday Checking',
      balance_cents INTEGER NOT NULL DEFAULT 0 CHECK(balance_cents >= 0),
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      reference TEXT NOT NULL UNIQUE,
      account_id INTEGER NOT NULL REFERENCES accounts(id),
      kind TEXT NOT NULL CHECK(kind IN ('DEPOSIT','WITHDRAWAL')),
      amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
      status TEXT NOT NULL CHECK(status IN ('COMPLETED','FAILED')),
      description TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_transactions_account_created
      ON transactions(account_id, created_at DESC);
    ''')
    username = os.environ.get('DEMO_USERNAME', 'demo_user')
    password = os.environ.get('DEMO_PASSWORD', 'ChangeMe-Immediately-123!')
    display_name = os.environ.get('DEMO_DISPLAY_NAME', 'Demo Customer')
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if not existing:
        cur = db.execute('INSERT INTO users(username,password_hash,display_name,created_at) VALUES(?,?,?,?)',
                         (username, generate_password_hash(password), display_name, now))
        user_id = cur.lastrowid
        db.execute('INSERT INTO accounts(user_id,account_number,account_type,balance_cents,created_at) VALUES(?,?,?,?,?)',
                   (user_id, '•••• 4821', 'Everyday Checking', 125000, now))
        db.execute('INSERT INTO accounts(user_id,account_number,account_type,balance_cents,created_at) VALUES(?,?,?,?,?)',
                   (user_id, '•••• 9074', 'Savings', 875000, now))
        db.commit()
    db.close()

init_db()


def csrf_token():
    token = session.get('_csrf_token')
    if token is None:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token
app.jinja_env.globals['csrf_token'] = csrf_token

@app.before_request
def csrf_protect():
    if request.method == 'POST':
        sent = request.form.get('_csrf_token', '')
        expected = session.get('_csrf_token', '')
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            abort(400, description='Your session token expired. Refresh the page and try again.')


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def money(cents):
    return f"${cents / 100:,.2f}"
app.jinja_env.filters['money'] = money


def get_accounts(user_id):
    return get_db().execute('SELECT * FROM accounts WHERE user_id = ? ORDER BY id', (user_id,)).fetchall()

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_db().execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['display_name'] = user['display_name']
            csrf_token()
            return redirect(url_for('dashboard'))
        flash('The username or password was not recognized.', 'error')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    accounts = get_accounts(session['user_id'])
    rows = db.execute('''SELECT t.*, a.account_number FROM transactions t
                         JOIN accounts a ON a.id=t.account_id
                         WHERE a.user_id=? ORDER BY t.created_at DESC, t.id DESC LIMIT 8''',
                      (session['user_id'],)).fetchall()
    total = sum(a['balance_cents'] for a in accounts)
    return render_template('dashboard.html', accounts=accounts, transactions=rows, total=total, active='dashboard')

@app.route('/transactions')
@login_required
def transactions():
    rows = get_db().execute('''SELECT t.*, a.account_number FROM transactions t
                               JOIN accounts a ON a.id=t.account_id
                               WHERE a.user_id=? ORDER BY t.created_at DESC, t.id DESC LIMIT 100''',
                            (session['user_id'],)).fetchall()
    return render_template('transactions.html', transactions=rows, active='transactions')

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    accounts = get_accounts(session['user_id'])
    if request.method == 'POST':
        account_id = request.form.get('account_id', type=int)
        amount_text = request.form.get('amount', '').strip()
        description = request.form.get('description', 'Demo deposit').strip()[:120] or 'Demo deposit'
        try:
            amount = Decimal(amount_text)
            cents = int(amount * 100)
            if amount <= 0 or amount != amount.quantize(Decimal('0.01')) or cents > 100000000:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            flash('Enter a valid amount with up to two decimal places.', 'error')
            return render_template('transaction_form.html', mode='deposit', accounts=accounts, active='deposit')
        db = get_db()
        account = db.execute('SELECT * FROM accounts WHERE id=? AND user_id=?', (account_id, session['user_id'])).fetchone()
        if not account:
            flash('Choose a valid account.', 'error')
            return render_template('transaction_form.html', mode='deposit', accounts=accounts, active='deposit')
        ref = 'DEMO-' + secrets.token_hex(5).upper()
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE accounts SET balance_cents=balance_cents+? WHERE id=?', (cents, account_id))
            db.execute('INSERT INTO transactions(reference,account_id,kind,amount_cents,status,description,created_at) VALUES(?,?,?,?,?,?,?)',
                       (ref, account_id, 'DEPOSIT', cents, 'COMPLETED', description, now))
            db.commit()
        except Exception:
            db.rollback()
            app.logger.exception('Demo deposit failed')
            flash('The demo deposit could not be processed. No change was made.', 'error')
            return render_template('transaction_form.html', mode='deposit', accounts=accounts, active='deposit')
        flash(f'Demo deposit completed. Reference: {ref}', 'success')
        return redirect(url_for('transactions'))
    return render_template('transaction_form.html', mode='deposit', accounts=accounts, active='deposit')

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    accounts = get_accounts(session['user_id'])
    if request.method == 'POST':
        account_id = request.form.get('account_id', type=int)
        amount_text = request.form.get('amount', '').strip()
        description = request.form.get('description', 'Demo withdrawal').strip()[:120] or 'Demo withdrawal'
        try:
            amount = Decimal(amount_text)
            cents = int(amount * 100)
            if amount <= 0 or amount != amount.quantize(Decimal('0.01')) or cents > 100000000:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            flash('Enter a valid amount with up to two decimal places.', 'error')
            return render_template('transaction_form.html', mode='withdraw', accounts=accounts, active='withdraw')
        db = get_db()
        account = db.execute('SELECT * FROM accounts WHERE id=? AND user_id=?', (account_id, session['user_id'])).fetchone()
        if not account:
            flash('Choose a valid account.', 'error')
            return render_template('transaction_form.html', mode='withdraw', accounts=accounts, active='withdraw')
        ref = 'DEMO-' + secrets.token_hex(5).upper()
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            db.execute('BEGIN IMMEDIATE')
            cur = db.execute('UPDATE accounts SET balance_cents=balance_cents-? WHERE id=? AND user_id=? AND balance_cents>=?',
                             (cents, account_id, session['user_id'], cents))
            if cur.rowcount != 1:
                db.rollback()
                flash('Insufficient available demo funds for this withdrawal.', 'error')
                return render_template('transaction_form.html', mode='withdraw', accounts=get_accounts(session['user_id']), active='withdraw')
            db.execute('INSERT INTO transactions(reference,account_id,kind,amount_cents,status,description,created_at) VALUES(?,?,?,?,?,?,?)',
                       (ref, account_id, 'WITHDRAWAL', cents, 'COMPLETED', description, now))
            db.commit()
        except Exception:
            db.rollback()
            app.logger.exception('Demo withdrawal failed')
            flash('The demo withdrawal could not be processed. No change was made.', 'error')
            return render_template('transaction_form.html', mode='withdraw', accounts=accounts, active='withdraw')
        flash(f'Demo withdrawal completed. Reference: {ref}', 'success')
        return redirect(url_for('transactions'))
    return render_template('transaction_form.html', mode='withdraw', accounts=accounts, active='withdraw')

@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', code=400, message=getattr(error, 'description', 'Bad request')), 400

@app.errorhandler(404)
def not_found(_error):
    return render_template('error.html', code=404, message='That page could not be found.'), 404

if __name__ == '__main__':
    # Local demo only. Do not expose the Flask development server to the public internet.
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')), debug=False)
