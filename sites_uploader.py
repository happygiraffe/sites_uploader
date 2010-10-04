#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Upload an attachment to a sites page."""

import getpass
import optparse
import os
import pickle
import sys

import gdata.data
import gdata.gauth
import gdata.sites.client
import gdata.sites.data

import oneshot

VERSION = '1.0'
SOURCE = 'Dom-SitesUploader-%s' % VERSION

# OAuth bits.  We use “anonymous” to behave as an unregistered application.
# http://code.google.com/apis/accounts/docs/OAuth_ref.html#SigningOAuth
CONSUMER_KEY = 'anonymous'
CONSUMER_SECRET = 'anonymous'
# TODO: limit scope to just what we actually need.
SCOPES = ['http://sites.google.com/feeds/',
          'https://sites.google.com/feeds/']

class Error(Exception):
  pass


class TokenStore(object):
  """Store and retreive OAuth access tokens."""

  def __init__(self, token_file=None):
    default = os.path.expanduser('~/.%s.tok' % os.path.basename(sys.argv[0]))
    self.token_file = token_file or default

  def ReadToken(self):
    """Read in the stored auth token object.

    Returns:
      The stored token object, or None.
    """
    if os.path.exists(self.token_file):
      fh = open(self.token_file, 'rb')
      tok = pickle.load(fh)
      fh.close()
      return tok
    else:
      return None

  def WriteToken(self, tok):
    """Write the token object to a file."""
    fh = open(self.token_file, 'wb')
    os.chmod(self.token_file, 0600)
    pickle.dump(tok, fh)
    fh.close()


class ClientAuthorizer(object):
  """Add authorization to a client."""

  def __init__(self, consumer_key=CONSUMER_KEY,
               consumer_secret=CONSUMER_SECRET, scopes=None,
               token_store=None):
    """Construct a new ClientAuthorizer."""
    self.consumer_key = consumer_key
    self.consumer_secret = consumer_secret
    self.scopes = scopes or SCOPES
    self.token_store = token_store or TokenStore()

  def FetchClientToken(self, client):
    """Ensure client.auth_token is valid.

    If a stored token is available, it will be used.  Otherwise, this goes
    through the OAuth rituals described at:

    http://code.google.com/apis/gdata/docs/auth/oauth.html#Examples
    """
    access_token = self.token_store.ReadToken()
    if not access_token:
      httpd = oneshot.ParamsReceiverServer()
      # TODO Find a way to pass "xoauth_displayname" parameter.
      request_token = client.GetOAuthToken(
          self.scopes, httpd.my_url(), self.consumer_key, self.consumer_secret)
      url = request_token.generate_authorization_url(google_apps_domain=client.domain)
      print 'Please visit this URL to continue authorization:'
      print url
      httpd.serve_until_result()
      request_token = gdata.gauth.AuthorizeRequestToken(request_token, httpd.result)
      access_token = client.GetAccessToken(request_token)
      self.token_store.WriteToken(access_token)
    client.auth_token = access_token


class SitesUploader(object):
  """A utility to upload a file to a sites page."""

  def __init__(self, domain, site, ssl=True, debug=False, client=None):
    """Construct a new SitesUploader.

    Args:
      domain: The google apps domain to upload to.
      site: The site within the domain.
      ssl: Boolean.  Should SSL be used for all connections? Default: True.
      debug: Boolean.  Should debug output be produced.  Default: False
      client: A gdata.sites.client.SitesClient object.  If not supplied, one
          will be created and populated with auth credentials on first use.
    """
    self.domain = domain
    self.site = site
    self.ssl = ssl
    self.debug = debug
    self.client = client

  def _MakeClient(self, client_authz=None):
    """Return a populated SitesClient object."""
    client = gdata.sites.client.SitesClient(source=SOURCE, site=self.site,
                                            domain=self.domain)
    client.ssl = self.ssl
    client.http_client.debug = self.debug
    # Make sure we've got a valid token in the client.
    if not client_authz:
      client_authz = ClientAuthorizer()
    client_authz.FetchClientToken(client)
    return client

  @property
  def _client(self):
    if not self.client:
      self.client = self._MakeClient()
    return self.client

  def _GetPage(self, client, page):
    """Return the ContentEntry for page.

    Throws:
      Error: if the page can't be found.
    """
    uri = '%s?path=%s' % (client.MakeContentFeedUri(), page)
    feed = client.GetContentFeed(uri)
    if not feed.entry:
      raise Error("can't find page %s" % page)
    return feed.entry[0]

  def _FindAttachment(self, client, page, media_source):
    """Return the attachment for media_source, or None."""
    # The id of the parent we need to query by isn't exposed directly, so we
    # parse it out of the id.  I'm not sure that this is the best way…
    uri = '%s?parent=%s&kind=attachment' % (client.MakeContentFeedUri(),
                                            os.path.basename(page.id.text))
    feed = client.GetContentFeed(uri)
    for entry in feed.GetAttachments():
      href = entry.GetAlternateLink().href
      # I'm not 100% happy with this check, but it appears to work.
      if os.path.basename(href) == media_source.file_name:
        return entry
    return None

  def UploadFile(self, page, to_upload):
    """Upload file to page.

    If file is already attached to page, it will be replaced.

    Args:
      page: The site-relative path to the page you wish to upload to.
      to_upload: A gdata.data.MediaSource object containing the file to upload.

    Returns:
      A ContentEntry object for the attachment.  The URL for the newly
      uploaded attachment is in GetAlternateLink().href.
    """
    client = self._client
    parent = self._GetPage(client, page)
    attachment = self._FindAttachment(client, parent, to_upload)
    if attachment:
      client.Update(attachment, media_source=to_upload)
    else:
      attachment = client.UploadAttachment(to_upload, parent)
    return attachment


def GetParser():
  """Return a populated OptionParser"""
  usage = u"""usage: %prog [options] /path/to/file

  Upload “file” to a page on the specified jotspot site.
  """
  parser = optparse.OptionParser(usage=usage, version=VERSION)
  parser.add_option('--domain', dest='domain', help='* Hosted domain')
  parser.add_option('--site', dest='site', help='* Site within domain')
  parser.add_option('--ssl', dest='ssl', action='store_true', default=False,
                    help='Use https for communications (%default)')
  parser.add_option('--debug', dest='debug', action='store_true', default=False,
                    help='Enable debug output (HTTP conversation)')
  parser.add_option('--content_type', dest='content_type',
                    default='application/octet-stream',
                    help='Content-type of file to be uploaded (%default)')
  parser.add_option('--page', dest='page', help='* Page to upload to')
  return parser


def main():
  parser = GetParser()
  (opts, args) = parser.parse_args()

  if len(args) == 0:
    parser.error('must specify file(s) to upload')

  if not opts.domain:
    parser.error('please specify --domain')

  if not opts.site:
    parser.error('please specify --site')

  if not opts.page:
    parser.error("please specify --page")

  if not opts.page.startswith('/'):
    opts.page = '/' + opts.page

  uploader = SitesUploader(opts.domain, opts.site, opts.ssl, opts.debug)
  for file_to_upload in args:
    if not os.path.exists(file_to_upload):
      raise Error("no such file: %s" % file_to_upload)
    media_source = gdata.data.MediaSource(file_path=file_to_upload,
                                          content_type=content_type)
    attachment = uploader.UploadFile(opts.page, media_source)
    print attachment.GetAlternateLink().href


if __name__ == '__main__':
  main()