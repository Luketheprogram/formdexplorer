"""Real Django SMTP transport against a loopback-only sink; it never relays mail."""
import socketserver
from threading import Thread
from unittest.mock import patch
from django.core.mail.backends.smtp import EmailBackend
from django.test import TestCase, override_settings
from django.utils import timezone
from filings.models import AlertDelivery
from filings.alerts.service import deliver
from .test_alert_delivery import Fixture, SMTP_SETTINGS


class Sink(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 local.test SMTP sink\r\n')
        while line:=self.rfile.readline():
            command=line.decode().strip().upper()
            if command.startswith(('EHLO','HELO')):self.wfile.write(b'250 local.test\r\n')
            elif command.startswith(('MAIL','RCPT','RSET','NOOP')):self.wfile.write(b'250 OK\r\n')
            elif command=='DATA':
                self.wfile.write(b'354 End with dot\r\n');body=[]
                while (row:=self.rfile.readline()) and row!=b'.\r\n':body.append(row)
                if self.server.reject:
                    self.server.reject=False;self.wfile.write(b'451 Try later\r\n')
                else:
                    self.server.messages.append(b''.join(body));self.wfile.write(b'250 Accepted\r\n')
            elif command=='QUIT':self.wfile.write(b'221 Bye\r\n');break
            else:self.wfile.write(b'500 Unknown\r\n')


@override_settings(**SMTP_SETTINGS)
class SMTPTransportTests(Fixture,TestCase):
    def setUp(self):
        self.make();self.d=self.queued()
        self.server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Sink)
        self.server.messages=[];self.server.reject=False
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.cleanup)
    def cleanup(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
    def backend(self,**kwargs):
        # Only this local sink bypasses TLS. Production configuration requires it.
        return EmailBackend(host='127.0.0.1',port=self.server.server_address[1],username='',password='',use_tls=False,use_ssl=False,timeout=3)
    def test_real_smtp_accepts_one_message_and_repeat_is_suppressed(self):
        with patch('filings.alerts.service.get_connection',side_effect=self.backend):
            self.assertEqual(deliver(self.d.pk),'sent');self.assertEqual(deliver(self.d.pk),'skipped')
        self.assertEqual(len(self.server.messages),1)
        message=self.server.messages[0]
        self.assertIn(b'To: researcher@example.test',message)
        self.assertIn(b'List-Unsubscribe-Post: List-Unsubscribe=One-Click',message)
        from email import policy
        from email.parser import BytesParser
        parsed=BytesParser(policy=policy.default).parsebytes(message)
        self.assertTrue(str(parsed['Message-ID']).strip().startswith('<filing-alert-'))
        self.assertIn('/one-click/',str(parsed['List-Unsubscribe']))
    def test_real_smtp_transient_rejection_then_retry_accepts_only_once(self):
        self.server.reject=True
        with patch('filings.alerts.service.get_connection',side_effect=self.backend):
            self.assertEqual(deliver(self.d.pk),'retry');self.assertEqual(self.server.messages,[])
            AlertDelivery.objects.filter(pk=self.d.pk).update(next_attempt_at=timezone.now())
            self.assertEqual(deliver(self.d.pk),'sent')
        self.assertEqual(len(self.server.messages),1)
