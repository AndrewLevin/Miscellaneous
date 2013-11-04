#!/usr/bin/env python
"""
_DQMUpload_

DQM upload script

Reads from a FWJR, finds the first analysis file
and uploads to the given URL (hopefully a DQM GUI url)
using the credentials in the environment.

Usage:

./DQMUpload.py fwjr.xml https://cmsweb-testbed.cern.ch:/dqm/dev

Adapted from:

https://github.com/rovere/dqmgui/blob/master/bin/visDQMUpload

and

https://github.com/dmwm/WMCore/blob/master/src/python/WMCore/WMSpec/Steps/Executors/DQMUpload.py

Created on Oct 10, 2012

@author: dballest
"""


from cStringIO import StringIO
from mimetypes import guess_type
from stat import *
from xml.dom.minidom import parse
import sys
import os.path
import urllib2
import httplib
import gzip
import traceback

try:
        from hashlib import md5
except ImportError:
        from md5 import md5

HTTPS = httplib.HTTPS
if sys.version_info[:3] >= (2, 4, 0):
    HTTPS = httplib.HTTPSConnection

ssl_key_file = None
ssl_cert_file = None

class HTTPSCertAuth(HTTPS):
    def __init__(self, host, *args, **kwargs):
        HTTPS.__init__(self, host, key_file = ssl_key_file, cert_file = ssl_cert_file, **kwargs)

class HTTPSCertAuthenticate(urllib2.AbstractHTTPHandler):
    def default_open(self, req):
        return self.do_open(HTTPSCertAuth, req)

def filetype(filename):
        return guess_type(filename)[0] or 'application/octet-stream'

def encode(args, files):
        """
        Encode form (name, value) and (name, filename, type) elements into
        multi-part/form-data. We don't actually need to know what we are
        uploading here, so just claim it's all text/plain.
        """
        boundary = '----------=_DQM_FILE_BOUNDARY_=-----------'
        (body, crlf) = ('', '\r\n')
        for (key, value) in args.items():
                payload = str(value)
                body += '--' + boundary + crlf
                body += ('Content-Disposition: form-data; name="%s"' % key) + crlf
                body += crlf + payload + crlf
        for (key, filename) in files.items():
                body += '--' + boundary + crlf
                body += ('Content-Disposition: form-data; name="%s"; filename="%s"'
                                 % (key, os.path.basename(filename))) + crlf
                body += ('Content-Type: %s' % filetype(filename)) + crlf
                body += ('Content-Length: %d' % os.path.getsize(filename)) + crlf
                body += crlf + open(filename, "r").read() + crlf
                body += '--' + boundary + '--' + crlf + crlf
        return ('multipart/form-data; boundary=' + boundary, body)

def marshall(args, files, request):
    """
        Marshalls the arguments to the CGI script as multi-part/form-data,
        not the default application/x-www-form-url-encoded.    This improves
        the transfer of the large inputs and eases command line invocation
        of the CGI script.
    """
    (contentType, body) = encode(args, files)
    request.add_header('Content-Type', contentType)
    request.add_header('Content-Length', str(len(body)))
    request.add_data(body)

def upload(url, args, files):
    ident = "visDQMUpload DQMGUI/%s python/%s" % \
        (os.getenv('DQMGUI_VERSION', '?'), "%d.%d.%d" % sys.version_info[:3])
    datareq = urllib2.Request(url + '/data/put')
    datareq.add_header('Accept-encoding', 'gzip')
    datareq.add_header('User-agent', ident)
    marshall(args, files, datareq)
    if 'https://' in url:
        result = urllib2.build_opener(HTTPSCertAuthenticate()).open(datareq)
    else:
        result = urllib2.build_opener(urllib2.ProxyHandler({})).open(datareq)

    data = result.read()
    if result.headers.get ('Content-encoding', '') == 'gzip':
        data = gzip.GzipFile (fileobj = StringIO(data)).read ()
    return (result.headers, data)

x509_path = os.getenv("X509_USER_PROXY", None)
if x509_path and os.path.exists(x509_path):
    ssl_key_file = ssl_cert_file = x509_path

if not ssl_key_file:
    x509_path = os.getenv("X509_USER_KEY", None)
    if x509_path and os.path.exists(x509_path):
        ssl_key_file = x509_path

if not ssl_cert_file:
    x509_path = os.getenv("X509_USER_CERT", None)
    if x509_path and os.path.exists(x509_path):
        ssl_cert_file = x509_path

if not ssl_key_file:
    x509_path = os.getenv("HOME") + "/.globus/userkey.pem"
    if os.path.exists(x509_path):
        ssl_key_file = x509_path

if not ssl_cert_file:
    x509_path = os.getenv("HOME") + "/.globus/usercert.pem"
    if os.path.exists(x509_path):
        ssl_cert_file = x509_path

if 'https://' in sys.argv[1] and (not ssl_key_file or not os.path.exists(ssl_key_file)):
    print >> sys.stderr, "no certificate private key file found"
    sys.exit(1)

if 'https://' in sys.argv[1] and (not ssl_cert_file or not os.path.exists(ssl_cert_file)):
    print >> sys.stderr, "no certificate public key file found"
    sys.exit(1)

print "Using SSL private key", ssl_key_file
print "Using SSL public key", ssl_cert_file

try:
    filename = (sys.argv[1]).encode('utf-8')

    blockSize = 0x10000

    def upd(m, data):
        m.update(data)
        return m

    fd = open(filename, 'rb')
    try:
        contents = iter(lambda: fd.read(blockSize), '')
        m = reduce(upd, contents, md5())
    finally:
        fd.close()

    (headers, data) = \
        upload(sys.argv[2],
                     { 'size': os.path.getsize(filename),
                         'checksum': "md5:%s" % m.hexdigest() },
                     { 'file': filename })
    print 'Status code: ', headers.get("Dqm-Status-Code", "None")
    print 'Message:         ', headers.get("Dqm-Status-Message", "None")
    print 'Detail:            ', headers.get("Dqm-Status-Detail", "None")
    print data
    sys.exit(0)
except urllib2.HTTPError, e:
    print "ERROR", e
    print 'Status code: ', e.hdrs.get("Dqm-Status-Code", "None")
    print 'Message:         ', e.hdrs.get("Dqm-Status-Message", "None")
    print 'Detail:            ', e.hdrs.get("Dqm-Status-Detail", "None")
    sys.exit(91)
except Exception, e:
    print "ERROR", e
    print traceback.format_exc()
    sys.exit(92)
