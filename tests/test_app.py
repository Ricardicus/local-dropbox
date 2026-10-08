import unittest, tempfile, os, json, pathlib

class VaultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        cls.tmp=tempfile.TemporaryDirectory()
        os.environ['DATA_DIR']=cls.tmp.name
        os.environ['MAX_FILE_MB']='1'
        os.environ['REQUIRE_STORAGE']='false'
        spec=importlib.util.spec_from_file_location('vault_test_server','server.py')
        cls.server=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.server)
        with cls.server.db() as c:
            c.execute('UPDATE users SET username=?,password=?', ('Anna',cls.server.password_hash('byxficka')))
        cls.cookie='';cls.csrf=''
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    @classmethod
    def req(cls,method,path,data=None,raw=False,auth=True,csrf=True):
        import io
        body=data if raw else json.dumps(data).encode() if data is not None else b''
        class Request(cls.server.Handler):
            def send_response(self,status):self.status=status
            def send_header(self,k,v):self.result_headers[k]=v
            def end_headers(self):pass
        h=Request.__new__(Request)
        h.path=path;h.client_address=('127.0.0.1',12345);h.headers={'Content-Length':str(len(body))}
        if auth:h.headers['Cookie']=cls.cookie
        if csrf:h.headers['X-CSRF-Token']=cls.csrf
        h.rfile=io.BytesIO(body);h.wfile=io.BytesIO();h.result_headers={}
        h.handle_request(method)
        return h.status,h.wfile.getvalue(),h.result_headers
    def test_http_requests_do_not_need_worker_threads(self):
        import io, types
        from unittest.mock import patch
        class Socket:
            def __init__(self, path):
                self.input=io.BytesIO(('GET '+path+' HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n').encode())
                self.output=bytearray()
            def makefile(self,*args,**kwargs):return self.input
            def settimeout(self,timeout):pass
            def sendall(self,data):self.output.extend(data)
        with patch('threading.Thread.start',side_effect=RuntimeError("can't start new thread")):
            for path in ('/', '/app.js', '/style.css', '/api/storage', '/favicon.ico'):
                socket=Socket(path)
                handler=self.server.Handler(socket,('127.0.0.1',12345),types.SimpleNamespace(server_name='localhost',server_port=8080))
                self.assertTrue(bytes(socket.output).startswith(b'HTTP/1.0 '))
                self.assertTrue(handler.close_connection)
                if path!='/favicon.ico':self.assertTrue(bytes(socket.output).startswith(b'HTTP/1.0 200 '))
        self.assertNotIn('ThreadingMixIn',[base.__name__ for base in self.server.HTTPServer.__mro__])

    def test_storage_loss_and_recovery(self):
        from unittest.mock import patch
        server=self.server
        marker=server.MARKER
        marker.touch()
        with patch.object(server, 'REQUIRE_STORAGE', True):
            self.assertTrue(json.loads(self.req('GET','/api/storage')[1])['available'])
            marker.unlink()
            status,html,headers=self.req('GET','/')
            self.assertEqual(status,200)
            self.assertIn(b'id="storage-error" class="storage-error" role="alert">',html)
            self.assertIn(server.STORAGE_ERROR.encode(),html)
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertFalse(json.loads(self.req('GET','/api/storage')[1])['available'])
            status,body,_=self.req('POST','/api/login',{'username':'Anna','password':'byxficka'})
            self.assertEqual(status,503)
            self.assertEqual(json.loads(body)['error'],server.STORAGE_ERROR)
            marker.touch()
            self.assertTrue(json.loads(self.req('GET','/api/storage')[1])['available'])
        marker.unlink()

    def test_empty_required_storage_is_not_initialized(self):
        import importlib.util
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as empty:
            with patch.dict(os.environ, {'DATA_DIR':str(pathlib.Path(empty)/'absent'), 'REQUIRE_STORAGE':'true'}):
                spec=importlib.util.spec_from_file_location('missing_storage_server','server.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                self.assertFalse(module.storage_available())
                self.assertEqual(list(pathlib.Path(empty).iterdir()),[])

    def test_workflow(self):
        status,_,_=self.req('GET','/api/items',auth=False);self.assertEqual(status,401)
        status,_,_=self.req('POST','/api/login',{'username':'Anna','password':'wrong'});self.assertEqual(status,401)
        status,b,h=self.req('POST','/api/login',{'username':'Anna','password':'byxficka'});self.assertEqual(status,200)
        type(self).cookie=h['Set-Cookie'].split(';')[0];type(self).csrf=json.loads(b)['csrf']
        self.assertIn('HttpOnly',h['Set-Cookie'])
        self.assertEqual(self.req('POST','/api/folders',{'name':'Work'},csrf=False)[0],403)
        self.assertEqual(self.req('POST','/api/folders',{'name':'Work'})[0],201)
        rows=json.loads(self.req('GET','/api/items')[1])['items'];folder=rows[0]['id']
        self.assertEqual(self.req('POST','/api/upload?name=notes.txt&parent='+folder,b'first',raw=True)[0],201)
        item=json.loads(self.req('GET','/api/items?parent='+folder)[1])['items'][0]['id']
        self.assertEqual(self.req('GET','/api/items/'+item+'/download',auth=False)[0],401)
        self.assertEqual(self.req('GET','/api/items/'+item+'/download')[1],b'first')
        self.assertEqual(self.req('POST','/api/upload?name=notes.txt&parent='+folder,b'duplicate',raw=True)[0],400)
        self.assertEqual(self.req('POST','/api/upload?name=x&replace='+item,b'updated',raw=True)[0],201)
        self.assertEqual(self.req('GET','/api/items/'+item+'/download')[1],b'updated')
        self.assertEqual(self.req('POST','/api/upload?name=big',b'x'*1048577,raw=True)[0],413)
        self.assertEqual(self.req('POST','/api/folders',{'name':'../escape'})[0],400)
        self.assertEqual(self.req('PATCH','/api/items/'+folder,{'parent':folder})[0],400)
        self.assertEqual(self.req('DELETE','/api/items/'+folder)[0],400)
        self.assertEqual(self.req('PATCH','/api/items/'+item,{'name':'renamed.txt','parent':None})[0],200)
        self.assertEqual(self.req('DELETE','/api/items/'+folder)[0],200)
        self.assertEqual(self.req('POST','/api/password',{'current':'wrong','password':'new-password-123'})[0],400)
        self.assertEqual(self.req('POST','/api/password',{'current':'byxficka','password':'new-password-123'})[0],200)
        self.assertEqual(self.req('POST','/api/logout',{})[0],200)
        self.assertEqual(self.req('GET','/api/items')[0],401)
        self.assertEqual(self.req('POST','/api/login',{'username':'Anna','password':'byxficka'})[0],401)
        status,b,h=self.req('POST','/api/login',{'username':'Anna','password':'new-password-123'});self.assertEqual(status,200)
        type(self).cookie=h['Set-Cookie'].split(';')[0];type(self).csrf=json.loads(b)['csrf']
        self.assertEqual(self.req('GET','/api/items/'+item+'/download')[1],b'updated')
        self.assertEqual(self.req('DELETE','/api/items/'+item)[0],200)
        self.assertEqual(list((pathlib.Path(self.tmp.name)/'files').iterdir()),[])

if __name__=='__main__':unittest.main()
