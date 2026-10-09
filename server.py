import os, json, sqlite3, secrets, hashlib, hmac, time, pathlib, mimetypes, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs, quote
from default_user import insert_default_user

DATA = pathlib.Path(os.environ.get('DATA_DIR', '/var/www/hallevault')).resolve()
REQUIRE_STORAGE = os.environ.get('REQUIRE_STORAGE', 'true').lower() == 'true'
STORAGE_ERROR = 'Lost contact with the mounted harddrive- ask Rickard to fix it.'
MARKER = DATA / '.hallevault-storage'
BLOBS = DATA / 'files'
PUBLIC = pathlib.Path(__file__).parent / 'public'
MAX_FILE = int(os.environ.get('MAX_FILE_MB', '200')) * 1024 * 1024
SECURE = os.environ.get('SECURE_COOKIES', 'false').lower() == 'true'
LOCK = threading.RLock()
ATTEMPTS = {}

def storage_available():
    try:
        return DATA.is_dir() and (not REQUIRE_STORAGE or MARKER.is_file()) and (DATA / 'vault.sqlite').is_file() and BLOBS.is_dir()
    except OSError:
        return False

def db():
    c = sqlite3.connect(DATA / 'vault.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def valid_password(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)

if not REQUIRE_STORAGE or MARKER.is_file():
    DATA.mkdir(parents=True, exist_ok=True)
    BLOBS.mkdir(exist_ok=True)
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,csrf TEXT,expires REAL);
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,parent TEXT REFERENCES items(id),name TEXT NOT NULL,kind TEXT NOT NULL,size INTEGER DEFAULT 0,blob TEXT,updated REAL,UNIQUE(parent,name));''')
        insert_default_user(c, password_hash)

class Handler(BaseHTTPRequestHandler):
    # Close every connection so idle keep-alive clients cannot block the next request.
    protocol_version = 'HTTP/1.0'
    def setup(self):
        super().setup()
        self.connection.settimeout(120)
    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args))
    def response(self, status, obj, headers=None):
        self.close_connection = True
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Connection','close')
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.security()
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def security(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    def body(self):
        n=int(self.headers.get('Content-Length',0))
        if n < 0 or n > 16384: raise ValueError('Request too large.')
        return json.loads(self.rfile.read(n) or b'{}')
    def session(self,c):
        cookies={}
        for part in self.headers.get('Cookie','').split(';'):
            if '=' in part:
                k,v=part.strip().split('=',1); cookies[k]=v
        token=hashlib.sha256(cookies.get('session','').encode()).hexdigest()
        return c.execute('SELECT sessions.*,users.username FROM sessions JOIN users ON users.id=user_id WHERE token=? AND expires>?',(token,time.time())).fetchone()
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PATCH(self): self.handle_request('PATCH')
    def do_DELETE(self): self.handle_request('DELETE')
    def handle_request(self,method):
        try:
            with LOCK:
                path = urlsplit(self.path).path
                if method == 'GET' and path in ('/', '/app.js', '/style.css'):
                    self.route(method, None)
                    return
                if method == 'GET' and path == '/api/storage':
                    available = storage_available()
                    self.response(200, {'available': available, 'error': None if available else STORAGE_ERROR})
                    return
                if not storage_available():
                    self.response(503, {'error': STORAGE_ERROR, 'code': 'STORAGE_UNAVAILABLE'})
                    return
                with db() as c: self.route(method,c)
        except (ValueError,KeyError,json.JSONDecodeError) as e:
            self.close_connection=True; self.response(400,{'error':str(e) or 'Invalid request.'})
        except sqlite3.IntegrityError:
            self.response(409,{'error':'That name is already used in this folder.'})
        except Exception as e:
            print('Request failed:',repr(e)); self.close_connection=True
            self.response(500,{'error':'The request could not be completed.'})
    def route(self,method,c):
        u=urlsplit(self.path); path=u.path; q=parse_qs(u.query)
        if method=='GET' and path in ('/','/app.js','/style.css'):
            f=PUBLIC / ('index.html' if path=='/' else path[1:]); b=f.read_bytes()
            if path == '/' and not storage_available():
                b = b.replace(b'<body>', b'<body class="storage-unavailable">').replace(b'id="storage-error" class="storage-error" role="alert" hidden', b'id="storage-error" class="storage-error" role="alert"').replace(b'id="login" class="login-screen"', b'id="login" class="login-screen" inert')
            self.send_response(200); self.send_header('Cache-Control','no-store'); self.send_header('Content-Type',mimetypes.guess_type(f.name)[0]); self.send_header('Content-Length',str(len(b))); self.security(); self.end_headers(); self.wfile.write(b); return
        if method=='POST' and path=='/api/login':
            ip=self.client_address[0]; now=time.time(); attempts=[t for t in ATTEMPTS.get(ip,[]) if t>now-300]; ATTEMPTS[ip]=attempts
            if len(attempts)>=10: self.response(429,{'error':'Too many attempts. Try again in five minutes.'}); return
            b=self.body(); user=c.execute('SELECT * FROM users WHERE lower(username)=lower(?)',(b.get('username',''),)).fetchone()
            if not user or not valid_password(b.get('password',''),user['password']):
                attempts.append(now); self.response(401,{'error':'Incorrect username or password.'}); return
            ATTEMPTS.pop(ip,None); token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
            c.execute('DELETE FROM sessions WHERE expires<?',(now,))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,now+86400))
            self.response(200,{'username':user['username'],'csrf':csrf}, {'Set-Cookie':'session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'+('; Secure' if SECURE else '')}); return
        s=self.session(c)
        if not s: self.response(401,{'error':'Please sign in.'}); return
        if method!='GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): self.response(403,{'error':'Invalid session. Reload the page.'}); return
        if path=='/api/me' and method=='GET': self.response(200,{'username':s['username'],'csrf':s['csrf'],'maxFileMB':MAX_FILE//1048576}); return
        if path=='/api/logout' and method=='POST':
            c.execute('DELETE FROM sessions WHERE token=?',(s['token'],)); self.response(200,{}, {'Set-Cookie':'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'}); return
        if path=='/api/password' and method=='POST':
            b=self.body(); old=c.execute('SELECT password FROM users WHERE id=?',(s['user_id'],)).fetchone()[0]
            if not valid_password(b.get('current',''),old): self.response(400,{'error':'Current password is incorrect.'}); return
            new=b.get('password','')
            if len(new)<10 or len(new)>1024: raise ValueError('Choose a password with 10–1024 characters.')
            c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(new),s['user_id']))
            c.execute('DELETE FROM sessions WHERE user_id=? AND token<>?',(s['user_id'],s['token']))
            self.response(200,{}); return
        if path=='/api/items' and method=='GET':
            parent=q.get('parent',[''])[0] or None; self.folder(c,parent)
            rows=c.execute('SELECT id,parent,name,kind,size,updated FROM items WHERE parent IS ? ORDER BY kind DESC,name COLLATE NOCASE',(parent,)).fetchall()
            crumbs=[]; p=parent
            while p:
                row=c.execute('SELECT id,parent,name FROM items WHERE id=?',(p,)).fetchone(); crumbs.insert(0,dict(row)); p=row['parent']
            used=c.execute("SELECT coalesce(sum(size),0) FROM items WHERE kind='file'").fetchone()[0]
            self.response(200,{'items':[dict(r) for r in rows],'breadcrumbs':crumbs,'used':used}); return
        if path=='/api/folders' and method=='POST':
            b=self.body(); name=self.name(b['name']); parent=b.get('parent') or None; self.folder(c,parent); self.unique(c,parent,name)
            c.execute('INSERT INTO items(id,parent,name,kind,updated) VALUES(?,?,?,?,?)',(secrets.token_hex(16),parent,name,'folder',time.time())); self.response(201,{}); return
        if path=='/api/upload' and method=='POST':
            parent=q.get('parent',[''])[0] or None; self.folder(c,parent); name=self.name(q.get('name',[''])[0]); replace=q.get('replace',[''])[0]
            existing=c.execute('SELECT * FROM items WHERE id=?',(replace,)).fetchone() if replace else None
            if replace and (not existing or existing['kind']!='file'): raise ValueError('File no longer exists.')
            if existing: name=existing['name']; parent=existing['parent']
            else: self.unique(c,parent,name)
            size=int(self.headers.get('Content-Length','-1'))
            if size<0 or size>MAX_FILE: self.close_connection=True; self.response(413,{'error':f'Files must be at most {MAX_FILE//1048576} MB.'}); return
            blob=secrets.token_hex(32); f=BLOBS/blob
            try:
                with f.open('xb') as out:
                    remaining=size
                    while remaining:
                        chunk=self.rfile.read(min(65536,remaining))
                        if not chunk: raise ValueError('Upload interrupted.')
                        out.write(chunk); remaining-=len(chunk)
                if existing:
                    c.execute('UPDATE items SET size=?,blob=?,updated=? WHERE id=?',(size,blob,time.time(),replace))
                else: c.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(16),parent,name,'file',size,blob,time.time()))
                c.commit()
            except Exception:
                f.unlink(missing_ok=True); raise
            if existing: (BLOBS/existing['blob']).unlink(missing_ok=True)
            self.response(201,{}); return
        if path.startswith('/api/items/'):
            ident=path.split('/')[3]; item=c.execute('SELECT * FROM items WHERE id=?',(ident,)).fetchone()
            if not item: self.response(404,{'error':'Item not found.'}); return
            if method=='GET' and path.endswith('/download') and item['kind']=='file':
                f=BLOBS/item['blob']
                with f.open('rb') as stream:
                    self.send_response(200); self.send_header('Content-Type','application/octet-stream'); self.send_header('Content-Length',str(item['size'])); self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(item['name'],safe='')); self.send_header('Cache-Control','no-store'); self.security(); self.end_headers()
                    while True:
                        chunk=stream.read(65536)
                        if not chunk: break
                        self.wfile.write(chunk)
                return
            if method=='PATCH':
                b=self.body(); name=self.name(b.get('name',item['name'])); parent=b.get('parent',item['parent']) or None; self.folder(c,parent)
                p=parent
                while p:
                    if p==ident: raise ValueError('A folder cannot be moved inside itself.')
                    p=c.execute('SELECT parent FROM items WHERE id=?',(p,)).fetchone()[0]
                self.unique(c,parent,name,ident); c.execute('UPDATE items SET name=?,parent=?,updated=? WHERE id=?',(name,parent,time.time(),ident)); self.response(200,{}); return
            if method=='DELETE':
                if c.execute('SELECT 1 FROM items WHERE parent=?',(ident,)).fetchone(): raise ValueError('Empty this folder before deleting it.')
                c.execute('DELETE FROM items WHERE id=?',(ident,)); c.commit()
                if item['blob']: (BLOBS/item['blob']).unlink(missing_ok=True)
                self.response(200,{}); return
        self.response(404,{'error':'Not found.'})
    def name(self,name):
        if not isinstance(name,str) or not name.strip() or len(name)>200 or name in ('.','..') or any(ord(x)<32 or x in '/\\' for x in name): raise ValueError('Use a name of 1–200 characters without slashes or control characters.')
        return name.strip()
    def folder(self,c,ident):
        if ident and not c.execute("SELECT 1 FROM items WHERE id=? AND kind='folder'",(ident,)).fetchone(): raise ValueError('Folder not found.')
    def unique(self,c,parent,name,exclude=''):
        if c.execute('SELECT 1 FROM items WHERE parent IS ? AND name=? AND id<>?',(parent,name,exclude)).fetchone(): raise ValueError('That name is already used in this folder. Use Replace to update a file.')

if __name__=='__main__':
    host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','8080'))
    print(f'Hallevault listening at http://{host}:{port}',flush=True)
    HTTPServer((host,port),Handler).serve_forever()
