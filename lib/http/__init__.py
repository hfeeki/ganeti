#
#

# Copyright (C) 2007, 2008 Google Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

"""HTTP module.

"""

import logging
import mimetools
import OpenSSL
import select
import socket
import errno

from cStringIO import StringIO

from ganeti import constants
from ganeti import serializer
from ganeti import utils


HTTP_GANETI_VERSION = "Ganeti %s" % constants.RELEASE_VERSION

HTTP_OK = 200
HTTP_NO_CONTENT = 204
HTTP_NOT_MODIFIED = 304

HTTP_0_9 = "HTTP/0.9"
HTTP_1_0 = "HTTP/1.0"
HTTP_1_1 = "HTTP/1.1"

HTTP_GET = "GET"
HTTP_HEAD = "HEAD"
HTTP_POST = "POST"
HTTP_PUT = "PUT"
HTTP_DELETE = "DELETE"

HTTP_ETAG = "ETag"
HTTP_HOST = "Host"
HTTP_SERVER = "Server"
HTTP_DATE = "Date"
HTTP_USER_AGENT = "User-Agent"
HTTP_CONTENT_TYPE = "Content-Type"
HTTP_CONTENT_LENGTH = "Content-Length"
HTTP_CONNECTION = "Connection"
HTTP_KEEP_ALIVE = "Keep-Alive"

_SSL_UNEXPECTED_EOF = "Unexpected EOF"

# Socket operations
(SOCKOP_SEND,
 SOCKOP_RECV,
 SOCKOP_SHUTDOWN) = range(3)

# send/receive quantum
SOCK_BUF_SIZE = 32768


class HttpError(Exception):
  """Internal exception for HTTP errors.

  This should only be used for internal error reporting.

  """


class HttpSocketTimeout(Exception):
  """Internal exception for socket timeouts.

  This should only be used for internal error reporting.

  """


class HttpException(Exception):
  code = None
  message = None

  def __init__(self, message=None):
    Exception.__init__(self)
    if message is not None:
      self.message = message


class HttpBadRequest(HttpException):
  code = 400


class HttpForbidden(HttpException):
  code = 403


class HttpNotFound(HttpException):
  code = 404


class HttpGone(HttpException):
  code = 410


class HttpLengthRequired(HttpException):
  code = 411


class HttpInternalError(HttpException):
  code = 500


class HttpNotImplemented(HttpException):
  code = 501


class HttpServiceUnavailable(HttpException):
  code = 503


class HttpVersionNotSupported(HttpException):
  code = 505


class HttpJsonConverter:
  CONTENT_TYPE = "application/json"

  def Encode(self, data):
    return serializer.DumpJson(data)

  def Decode(self, data):
    return serializer.LoadJson(data)


def WaitForSocketCondition(poller, sock, event, timeout):
  """Waits for a condition to occur on the socket.

  @type poller: select.Poller
  @param poller: Poller object as created by select.poll()
  @type sock: socket
  @param sock: Wait for events on this socket
  @type event: int
  @param event: ORed condition (see select module)
  @type timeout: float or None
  @param timeout: Timeout in seconds
  @rtype: int or None
  @return: None for timeout, otherwise occured conditions

  """
  check = (event | select.POLLPRI |
           select.POLLNVAL | select.POLLHUP | select.POLLERR)

  if timeout is not None:
    # Poller object expects milliseconds
    timeout *= 1000

  poller.register(sock, event)
  try:
    while True:
      # TODO: If the main thread receives a signal and we have no timeout, we
      # could wait forever. This should check a global "quit" flag or
      # something every so often.
      io_events = poller.poll(timeout)
      if not io_events:
        # Timeout
        return None
      for (evfd, evcond) in io_events:
        if evcond & check:
          return evcond
  finally:
    poller.unregister(sock)


def SocketOperation(poller, sock, op, arg1, timeout):
  """Wrapper around socket functions.

  This function abstracts error handling for socket operations, especially
  for the complicated interaction with OpenSSL.

  @type poller: select.Poller
  @param poller: Poller object as created by select.poll()
  @type sock: socket
  @param sock: Socket for the operation
  @type op: int
  @param op: Operation to execute (SOCKOP_* constants)
  @type arg1: any
  @param arg1: Parameter for function (if needed)
  @type timeout: None or float
  @param timeout: Timeout in seconds or None
  @return: Return value of socket function

  """
  # TODO: event_poll/event_check/override
  if op == SOCKOP_SEND:
    event_poll = select.POLLOUT
    event_check = select.POLLOUT

  elif op == SOCKOP_RECV:
    event_poll = select.POLLIN
    event_check = select.POLLIN | select.POLLPRI

  elif op == SOCKOP_SHUTDOWN:
    event_poll = None
    event_check = None

    # The timeout is only used when OpenSSL requests polling for a condition.
    # It is not advisable to have no timeout for shutdown.
    assert timeout

  else:
    raise AssertionError("Invalid socket operation")

  # No override by default
  event_override = 0

  while True:
    # Poll only for certain operations and when asked for by an override
    if event_override or op in (SOCKOP_SEND, SOCKOP_RECV):
      if event_override:
        wait_for_event = event_override
      else:
        wait_for_event = event_poll

      event = WaitForSocketCondition(poller, sock, wait_for_event, timeout)
      if event is None:
        raise HttpSocketTimeout()

      if (op == SOCKOP_RECV and
          event & (select.POLLNVAL | select.POLLHUP | select.POLLERR)):
        return ""

      if not event & wait_for_event:
        continue

    # Reset override
    event_override = 0

    try:
      try:
        if op == SOCKOP_SEND:
          return sock.send(arg1)

        elif op == SOCKOP_RECV:
          return sock.recv(arg1)

        elif op == SOCKOP_SHUTDOWN:
          if isinstance(sock, OpenSSL.SSL.ConnectionType):
            # PyOpenSSL's shutdown() doesn't take arguments
            return sock.shutdown()
          else:
            return sock.shutdown(arg1)

      except OpenSSL.SSL.WantWriteError:
        # OpenSSL wants to write, poll for POLLOUT
        event_override = select.POLLOUT
        continue

      except OpenSSL.SSL.WantReadError:
        # OpenSSL wants to read, poll for POLLIN
        event_override = select.POLLIN | select.POLLPRI
        continue

      except OpenSSL.SSL.WantX509LookupError:
        continue

      except OpenSSL.SSL.SysCallError, err:
        if op == SOCKOP_SEND:
          # arg1 is the data when writing
          if err.args and err.args[0] == -1 and arg1 == "":
            # errors when writing empty strings are expected
            # and can be ignored
            return 0

        elif op == SOCKOP_RECV:
          if err.args == (-1, _SSL_UNEXPECTED_EOF):
            return ""

        raise socket.error(err.args)

      except OpenSSL.SSL.Error, err:
        raise socket.error(err.args)

    except socket.error, err:
      if err.args and err.args[0] == errno.EAGAIN:
        # Ignore EAGAIN
        continue

      raise


def ShutdownConnection(poller, sock, close_timeout, write_timeout, msgreader,
                       force):
  """Closes the connection.

  @type poller: select.Poller
  @param poller: Poller object as created by select.poll()
  @type sock: socket
  @param sock: Socket to be shut down
  @type close_timeout: float
  @param close_timeout: How long to wait for the peer to close the connection
  @type write_timeout: float
  @param write_timeout: Write timeout for shutdown
  @type msgreader: http.HttpMessageReader
  @param msgreader: Request message reader, used to determine whether peer
                    should close connection
  @type force: bool
  @param force: Whether to forcibly close the connection without waiting
                for peer

  """
  poller = select.poll()

  #print msgreader.peer_will_close, force
  if msgreader and msgreader.peer_will_close and not force:
    # Wait for peer to close
    try:
      # Check whether it's actually closed
      if not SocketOperation(poller, sock, SOCKOP_RECV, 1, close_timeout):
        return
    except (socket.error, HttpError, HttpSocketTimeout):
      # Ignore errors at this stage
      pass

  # Close the connection from our side
  try:
    SocketOperation(poller, sock, SOCKOP_SHUTDOWN, socket.SHUT_RDWR,
                    write_timeout)
  except HttpSocketTimeout:
    raise HttpError("Timeout while shutting down connection")
  except socket.error, err:
    raise HttpError("Error while shutting down connection: %s" % err)


class HttpSslParams(object):
  """Data class for SSL key and certificate.

  """
  def __init__(self, ssl_key_path, ssl_cert_path):
    """Initializes this class.

    @type ssl_key_path: string
    @param ssl_key_path: Path to file containing SSL key in PEM format
    @type ssl_cert_path: string
    @param ssl_cert_path: Path to file containing SSL certificate in PEM format

    """
    self.ssl_key_pem = utils.ReadFile(ssl_key_path)
    self.ssl_cert_pem = utils.ReadFile(ssl_cert_path)

  def GetKey(self):
    return OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM,
                                          self.ssl_key_pem)

  def GetCertificate(self):
    return OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM,
                                           self.ssl_cert_pem)


class HttpBase(object):
  """Base class for HTTP server and client.

  """
  def __init__(self):
    self.using_ssl = None
    self._ssl_params = None
    self._ssl_key = None
    self._ssl_cert = None

  def _CreateSocket(self, ssl_params, ssl_verify_peer):
    """Creates a TCP socket and initializes SSL if needed.

    @type ssl_params: HttpSslParams
    @param ssl_params: SSL key and certificate
    @type ssl_verify_peer: bool
    @param ssl_verify_peer: Whether to require client certificate and compare
                            it with our certificate

    """
    self._ssl_params = ssl_params

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Should we enable SSL?
    self.using_ssl = ssl_params is not None

    if not self.using_ssl:
      return sock

    self._ssl_key = ssl_params.GetKey()
    self._ssl_cert = ssl_params.GetCertificate()

    ctx = OpenSSL.SSL.Context(OpenSSL.SSL.SSLv23_METHOD)
    ctx.set_options(OpenSSL.SSL.OP_NO_SSLv2)

    ctx.use_privatekey(self._ssl_key)
    ctx.use_certificate(self._ssl_cert)
    ctx.check_privatekey()

    if ssl_verify_peer:
      ctx.set_verify(OpenSSL.SSL.VERIFY_PEER |
                     OpenSSL.SSL.VERIFY_FAIL_IF_NO_PEER_CERT,
                     self._SSLVerifyCallback)

    return OpenSSL.SSL.Connection(ctx, sock)

  def _SSLVerifyCallback(self, conn, cert, errnum, errdepth, ok):
    """Verify the certificate provided by the peer

    We only compare fingerprints. The client must use the same certificate as
    we do on our side.

    """
    assert self._ssl_params, "SSL not initialized"

    return (self._ssl_cert.digest("sha1") == cert.digest("sha1") and
            self._ssl_cert.digest("md5") == cert.digest("md5"))


class HttpMessage(object):
  """Data structure for HTTP message.

  """
  def __init__(self):
    self.start_line = None
    self.headers = None
    self.body = None
    self.decoded_body = None


class HttpClientToServerStartLine(object):
  """Data structure for HTTP request start line.

  """
  def __init__(self, method, path, version):
    self.method = method
    self.path = path
    self.version = version

  def __str__(self):
    return "%s %s %s" % (self.method, self.path, self.version)


class HttpServerToClientStartLine(object):
  """Data structure for HTTP response start line.

  """
  def __init__(self, version, code, reason):
    self.version = version
    self.code = code
    self.reason = reason

  def __str__(self):
    return "%s %s %s" % (self.version, self.code, self.reason)


class HttpMessageWriter(object):
  """Writes an HTTP message to a socket.

  """
  def __init__(self, sock, msg, write_timeout):
    """Initializes this class and writes an HTTP message to a socket.

    @type sock: socket
    @param sock: Socket to be written to
    @type msg: http.HttpMessage
    @param msg: HTTP message to be written
    @type write_timeout: float
    @param write_timeout: Write timeout for socket

    """
    self._msg = msg

    self._PrepareMessage()

    buf = self._FormatMessage()

    poller = select.poll()

    pos = 0
    end = len(buf)
    while pos < end:
      # Send only SOCK_BUF_SIZE bytes at a time
      data = buf[pos:(pos + SOCK_BUF_SIZE)]

      sent = SocketOperation(poller, sock, SOCKOP_SEND, data,
                             write_timeout)

      # Remove sent bytes
      pos += sent

    assert pos == end, "Message wasn't sent completely"

  def _PrepareMessage(self):
    """Prepares the HTTP message by setting mandatory headers.

    """
    # RFC2616, section 4.3: "The presence of a message-body in a request is
    # signaled by the inclusion of a Content-Length or Transfer-Encoding header
    # field in the request's message-headers."
    if self._msg.body:
      self._msg.headers[HTTP_CONTENT_LENGTH] = len(self._msg.body)

  def _FormatMessage(self):
    """Serializes the HTTP message into a string.

    """
    buf = StringIO()

    # Add start line
    buf.write(str(self._msg.start_line))
    buf.write("\r\n")

    # Add headers
    if self._msg.start_line.version != HTTP_0_9:
      for name, value in self._msg.headers.iteritems():
        buf.write("%s: %s\r\n" % (name, value))

    buf.write("\r\n")

    # Add message body if needed
    if self.HasMessageBody():
      buf.write(self._msg.body)

    elif self._msg.body:
      logging.warning("Ignoring message body")

    return buf.getvalue()

  def HasMessageBody(self):
    """Checks whether the HTTP message contains a body.

    Can be overriden by subclasses.

    """
    return bool(self._msg.body)


class HttpMessageReader(object):
  """Reads HTTP message from socket.

  """
  # Length limits
  START_LINE_LENGTH_MAX = None
  HEADER_LENGTH_MAX = None

  # Parser state machine
  PS_START_LINE = "start-line"
  PS_HEADERS = "headers"
  PS_BODY = "entity-body"
  PS_COMPLETE = "complete"

  def __init__(self, sock, msg, read_timeout):
    """Reads an HTTP message from a socket.

    @type sock: socket
    @param sock: Socket to be read from
    @type msg: http.HttpMessage
    @param msg: Object for the read message
    @type read_timeout: float
    @param read_timeout: Read timeout for socket

    """
    self.sock = sock
    self.msg = msg

    self.poller = select.poll()
    self.start_line_buffer = None
    self.header_buffer = StringIO()
    self.body_buffer = StringIO()
    self.parser_status = self.PS_START_LINE
    self.content_length = None
    self.peer_will_close = None

    buf = ""
    eof = False
    while self.parser_status != self.PS_COMPLETE:
      data = SocketOperation(self.poller, sock, SOCKOP_RECV, SOCK_BUF_SIZE,
                             read_timeout)

      if data:
        buf += data
      else:
        eof = True

      # Do some parsing and error checking while more data arrives
      buf = self._ContinueParsing(buf, eof)

      # Must be done only after the buffer has been evaluated
      # TODO: Connection-length < len(data read) and connection closed
      if (eof and
          self.parser_status in (self.PS_START_LINE,
                                 self.PS_HEADERS)):
        raise HttpError("Connection closed prematurely")

    # Parse rest
    buf = self._ContinueParsing(buf, True)

    assert self.parser_status == self.PS_COMPLETE
    assert not buf, "Parser didn't read full response"

    msg.body = self.body_buffer.getvalue()

    # TODO: Content-type, error handling
    if msg.body:
      msg.decoded_body = HttpJsonConverter().Decode(msg.body)
    else:
      msg.decoded_body = None

    if msg.decoded_body:
      logging.debug("Message body: %s", msg.decoded_body)

  def _ContinueParsing(self, buf, eof):
    """Main function for HTTP message state machine.

    @type buf: string
    @param buf: Receive buffer
    @type eof: bool
    @param eof: Whether we've reached EOF on the socket
    @rtype: string
    @return: Updated receive buffer

    """
    if self.parser_status == self.PS_START_LINE:
      # Expect start line
      while True:
        idx = buf.find("\r\n")

        # RFC2616, section 4.1: "In the interest of robustness, servers SHOULD
        # ignore any empty line(s) received where a Request-Line is expected.
        # In other words, if the server is reading the protocol stream at the
        # beginning of a message and receives a CRLF first, it should ignore
        # the CRLF."
        if idx == 0:
          # TODO: Limit number of CRLFs/empty lines for safety?
          buf = buf[:2]
          continue

        if idx > 0:
          self.start_line_buffer = buf[:idx]

          self._CheckStartLineLength(len(self.start_line_buffer))

          # Remove status line, including CRLF
          buf = buf[idx + 2:]

          self.msg.start_line = self.ParseStartLine(self.start_line_buffer)

          self.parser_status = self.PS_HEADERS
        else:
          # Check whether incoming data is getting too large, otherwise we just
          # fill our read buffer.
          self._CheckStartLineLength(len(buf))

        break

    # TODO: Handle messages without headers
    if self.parser_status == self.PS_HEADERS:
      # Wait for header end
      idx = buf.find("\r\n\r\n")
      if idx >= 0:
        self.header_buffer.write(buf[:idx + 2])

        self._CheckHeaderLength(self.header_buffer.tell())

        # Remove headers, including CRLF
        buf = buf[idx + 4:]

        self._ParseHeaders()

        self.parser_status = self.PS_BODY
      else:
        # Check whether incoming data is getting too large, otherwise we just
        # fill our read buffer.
        self._CheckHeaderLength(len(buf))

    if self.parser_status == self.PS_BODY:
      # TODO: Implement max size for body_buffer
      self.body_buffer.write(buf)
      buf = ""

      # Check whether we've read everything
      #
      # RFC2616, section 4.4: "When a message-body is included with a message,
      # the transfer-length of that body is determined by one of the following
      # [...] 5. By the server closing the connection. (Closing the connection
      # cannot be used to indicate the end of a request body, since that would
      # leave no possibility for the server to send back a response.)"
      if (eof or
          self.content_length is None or
          (self.content_length is not None and
           self.body_buffer.tell() >= self.content_length)):
        self.parser_status = self.PS_COMPLETE

    return buf

  def _CheckStartLineLength(self, length):
    """Limits the start line buffer size.

    @type length: int
    @param length: Buffer size

    """
    if (self.START_LINE_LENGTH_MAX is not None and
        length > self.START_LINE_LENGTH_MAX):
      raise HttpError("Start line longer than %d chars" %
                       self.START_LINE_LENGTH_MAX)

  def _CheckHeaderLength(self, length):
    """Limits the header buffer size.

    @type length: int
    @param length: Buffer size

    """
    if (self.HEADER_LENGTH_MAX is not None and
        length > self.HEADER_LENGTH_MAX):
      raise HttpError("Headers longer than %d chars" % self.HEADER_LENGTH_MAX)

  def ParseStartLine(self, start_line):
    """Parses the start line of a message.

    Must be overriden by subclass.

    @type start_line: string
    @param start_line: Start line string

    """
    raise NotImplementedError()

  def _WillPeerCloseConnection(self):
    """Evaluate whether peer will close the connection.

    @rtype: bool
    @return: Whether peer will close the connection

    """
    # RFC2616, section 14.10: "HTTP/1.1 defines the "close" connection option
    # for the sender to signal that the connection will be closed after
    # completion of the response. For example,
    #
    #        Connection: close
    #
    # in either the request or the response header fields indicates that the
    # connection SHOULD NOT be considered `persistent' (section 8.1) after the
    # current request/response is complete."

    hdr_connection = self.msg.headers.get(HTTP_CONNECTION, None)
    if hdr_connection:
      hdr_connection = hdr_connection.lower()

    # An HTTP/1.1 server is assumed to stay open unless explicitly closed.
    if self.msg.start_line.version == HTTP_1_1:
      return (hdr_connection and "close" in hdr_connection)

    # Some HTTP/1.0 implementations have support for persistent connections,
    # using rules different than HTTP/1.1.

    # For older HTTP, Keep-Alive indicates persistent connection.
    if self.msg.headers.get(HTTP_KEEP_ALIVE):
      return False

    # At least Akamai returns a "Connection: Keep-Alive" header, which was
    # supposed to be sent by the client.
    if hdr_connection and "keep-alive" in hdr_connection:
      return False

    return True

  def _ParseHeaders(self):
    """Parses the headers.

    This function also adjusts internal variables based on header values.

    RFC2616, section 4.3: "The presence of a message-body in a request is
    signaled by the inclusion of a Content-Length or Transfer-Encoding header
    field in the request's message-headers."

    """
    # Parse headers
    self.header_buffer.seek(0, 0)
    self.msg.headers = mimetools.Message(self.header_buffer, 0)

    self.peer_will_close = self._WillPeerCloseConnection()

    # Do we have a Content-Length header?
    hdr_content_length = self.msg.headers.get(HTTP_CONTENT_LENGTH, None)
    if hdr_content_length:
      try:
        self.content_length = int(hdr_content_length)
      except ValueError:
        self.content_length = None
      if self.content_length is not None and self.content_length < 0:
        self.content_length = None

    # if the connection remains open and a content-length was not provided,
    # then assume that the connection WILL close.
    if self.content_length is None:
      self.peer_will_close = True