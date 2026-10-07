import hashlib,hmac,secrets,sqlite3,time,uuid,re,threading
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field
from . import storage
from .config import setting

router=APIRouter(prefix='/api/auth',tags=['accounts'])
COOKIE=setting('APP_COOKIE_NAME','shitu_session');SESSION_SECONDS=7*86400;HASH_SLOTS=threading.BoundedSemaphore(2)

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def hash_password(password):
    salt=secrets.token_bytes(16)
    with HASH_SLOTS:derived=hashlib.scrypt(password.encode(),salt=salt,n=2**17,r=8,p=1,maxmem=256*1024*1024,dklen=32)
    return 'scrypt$131072$'+salt.hex()+'$'+derived.hex()

def verify_password(password,value):
    try:
        algorithm,n,salt,expected=value.split('$')
        if algorithm!='scrypt' or int(n)!=2**17:return False
        with HASH_SLOTS:actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=int(n),r=8,p=1,maxmem=256*1024*1024,dklen=32)
        return hmac.compare_digest(actual.hex(),expected)
    except (ValueError,TypeError):return False

DUMMY_HASH=hash_password(secrets.token_hex(16))

def public_user(row):return {'id':row['id'],'username':row['username'],'nickname':row['nickname'],'created':row['created']}

def user_by_name(name):
    with storage.connect() as c:
        c.row_factory=sqlite3.Row;r=c.execute('SELECT * FROM users WHERE username=?',(name.lower().strip(),)).fetchone()
    return dict(r) if r else None

def throttle(request,name=''):
    ip=request.client.host if request.client else 'unknown';now=time.time()
    buckets=[('ip:'+digest(ip),40)]
    if name:buckets.append(('name:'+digest(name.lower().strip()),12))
    with storage.connect() as c:
        c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM auth_attempts WHERE time<?',(now-900,))
        for bucket,limit in buckets:
            if c.execute('SELECT COUNT(*) FROM auth_attempts WHERE bucket=?',(bucket,)).fetchone()[0]>=limit:
                raise HTTPException(429,'尝试次数较多，请15分钟后再试',headers={'Retry-After':'900'})
        c.executemany('INSERT INTO auth_attempts VALUES(?,?)',[(b,now) for b,_ in buckets])

def current_user(request:Request):
    token=request.cookies.get(COOKIE,'')
    with storage.connect() as c:
        c.row_factory=sqlite3.Row
        r=c.execute('SELECT users.*,sessions.csrf,sessions.token_hash FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(digest(token),time.time())).fetchone()
    if not r:raise HTTPException(401,'请先登录，或登录状态已过期')
    user=dict(r)
    if request.method not in ('GET','HEAD','OPTIONS') and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),user['csrf']):
        raise HTTPException(403,'请求校验失败，请刷新页面后重试')
    return user

def set_session(response,user):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    with storage.connect() as c:
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token),user['id'],csrf,time.time()+SESSION_SECONDS,storage.now()))
    response.set_cookie(COOKIE,token,max_age=SESSION_SECONDS,httponly=True,secure=setting('APP_PUBLIC_ORIGIN','http://127.0.0.1:8767').startswith('https://'),samesite='strict',path='/')
    return {'user':public_user(user),'csrf_token':csrf}

class Credentials(BaseModel):
    username:str=Field(min_length=3,max_length=32)
    password:str=Field(min_length=12,max_length=128)

class Registration(Credentials):nickname:str=Field(default='',max_length=30)

@router.post('/register',status_code=201)
def register(body:Registration,request:Request,response:Response):
    name=body.username.lower().strip();throttle(request,name)
    if not re.fullmatch(r'[a-z0-9_.-]{3,32}',name):raise HTTPException(400,'用户名使用3至32位字母、数字、下划线、点或短横线')
    recovery=secrets.token_urlsafe(24)
    user=dict(id=uuid.uuid4().hex,username=name,nickname=body.nickname.strip() or name,password_hash=hash_password(body.password),recovery_hash=digest(recovery),created=storage.now())
    try:
        with storage.connect() as c:c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',tuple(user[k] for k in ('id','username','nickname','password_hash','recovery_hash','created')))
    except sqlite3.IntegrityError:raise HTTPException(409,'该用户名已经注册，请登录或换一个用户名') from None
    return {**set_session(response,user),'recovery_code':recovery}

@router.post('/login')
def login(body:Credentials,request:Request,response:Response):
    throttle(request,body.username);user=user_by_name(body.username)
    valid=verify_password(body.password,user['password_hash'] if user else DUMMY_HASH)
    if not user or not valid:raise HTTPException(401,'用户名或密码不正确')
    return set_session(response,user)

@router.get('/me')
def me(user=Depends(current_user)):return {'user':public_user(user),'csrf_token':user['csrf']}

@router.post('/logout')
def logout(response:Response,user=Depends(current_user)):
    with storage.connect() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(user['token_hash'],))
    response.delete_cookie(COOKIE,path='/');return {'ok':True}

class Profile(BaseModel):nickname:str=Field(min_length=1,max_length=30)

@router.patch('/profile')
def profile(body:Profile,user=Depends(current_user)):
    name=body.nickname.strip()
    if not name:raise HTTPException(400,'昵称不能为空')
    with storage.connect() as c:c.execute('UPDATE users SET nickname=? WHERE id=?',(name,user['id']))
    user['nickname']=name;return {'user':public_user(user)}

class PasswordChange(BaseModel):
    current_password:str=Field(min_length=1,max_length=128)
    new_password:str=Field(min_length=12,max_length=128)

@router.post('/password')
def password(body:PasswordChange,request:Request,response:Response,user=Depends(current_user)):
    throttle(request,user['username'])
    if not verify_password(body.current_password,user['password_hash']):raise HTTPException(400,'当前密码不正确')
    value=hash_password(body.new_password)
    with storage.connect() as c:
        changed=c.execute('UPDATE users SET password_hash=? WHERE id=? AND password_hash=?',(value,user['id'],user['password_hash'])).rowcount
        if not changed:raise HTTPException(409,'账户密码已被更新，请重新登录后操作')
        c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    return set_session(response,user)

class Recovery(BaseModel):
    username:str=Field(min_length=3,max_length=32)
    recovery_code:str=Field(min_length=10,max_length=100)
    new_password:str=Field(min_length=12,max_length=128)

@router.post('/recover')
def recover(body:Recovery,request:Request,response:Response):
    throttle(request,body.username);user=user_by_name(body.username)
    if not user or not hmac.compare_digest(digest(body.recovery_code.strip()),user['recovery_hash']):raise HTTPException(400,'用户名或恢复码不正确')
    code=secrets.token_urlsafe(24);value=hash_password(body.new_password)
    with storage.connect() as c:
        # A recovery code can be consumed once, even by concurrent requests.
        changed=c.execute('UPDATE users SET password_hash=?,recovery_hash=? WHERE id=? AND recovery_hash=?',(value,digest(code),user['id'],user['recovery_hash'])).rowcount
        if not changed:raise HTTPException(400,'恢复码已失效')
        c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    return {**set_session(response,user),'recovery_code':code}

class Confirmation(BaseModel):password:str=Field(min_length=1,max_length=128)

@router.post('/recovery-code')
def rotate_recovery(body:Confirmation,request:Request,user=Depends(current_user)):
    throttle(request,user['username'])
    if not verify_password(body.password,user['password_hash']):raise HTTPException(400,'密码不正确')
    code=secrets.token_urlsafe(24)
    with storage.connect() as c:c.execute('UPDATE users SET recovery_hash=? WHERE id=?',(digest(code),user['id']))
    return {'recovery_code':code}
