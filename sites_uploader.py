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

class ClientAuthorizer():
  """Add authorization to a client."""

  def __init__(self, consumer_key=CONSUMER_KEY,
               consumer_secret=CONSUMER_SECRET, scopes=None):
    """Construct a new ClientAuthorizer."""
    self.consumer_key = consumer_key
    self.consumer_secret = consumer_secret
    if scopes:
      self.scopes = scopes
    else:
      self.scopes = SCOPES
    self.tokfile = os.path.expanduser('~/.%s.tok' % os.path.basename(sys.argv[0]))

  def ReadToken(self):
    """Read in the stored auth token object.

    Returns:
      The stored token object, or None.
    """
    if os.path.exists(self.tokfile):
      fh = open(self.tokfile, 'rb')
      tok = pickle.load(fh)
      fh.close()
      return tok
    else:
      return None

  def WriteToken(self, tok):
    """Write the token object to a file."""
    fh = open(self.tokfile, 'wb')
    os.chmod(self.tokfile, 0600)
    pickle.dump(tok, fh)
    fh.close()

  def FetchClientToken(self, client):
    """Ensure client.auth_token is valid.

    If a stored token is available, it will be used.  Otherwise, this goes
    through the OAuth rituals described at:

    http://code.google.com/apis/gdata/docs/auth/oauth.html#Examples
    """
    access_token = self.ReadToken()
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
      self.WriteToken(access_token)
    client.auth_token = access_token

def die(msg):
  me = os.path.basename(sys.argv[0])
  print >>sys.stderr, me + ": " + msg
  sys.exit(1)

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

def GetClient(site, domain, ssl, debug=False, client_authz=ClientAuthorizer):
  """Return a populated SitesClient object."""
  client = gdata.sites.client.SitesClient(source=SOURCE, site=site,
                                          domain=domain)
  client.ssl = ssl
  client.http_client.debug = debug
  # Make sure we've got a valid token in the client.
  client_authz().FetchClientToken(client)
  return client

def GetPage(client, page):
  """Return the ContentEntry for page."""
  uri = '%s?path=%s' % (client.MakeContentFeedUri(), page)
  feed = client.GetContentFeed(uri)
  if not feed.entry:
    die("can't find page %s" % opts.page)
  return feed.entry[0]

def FindAttachment(client, page, media_source):
  """Return the attachment for media_source, or None."""
  uri = '%s?parent=%s&kind=attachment' % (client.MakeContentFeedUri(),
                                          os.path.basename(page.id.text))
  feed = client.GetContentFeed(uri)
  for entry in feed.entry:
    href = entry.GetAlternateLink().href
    # I'm not 100% happy with this check, but it appears to work.
    if os.path.basename(href) == media_source.file_name:
      return entry
  return None

def main():
  parser = GetParser()
  (opts, args) = parser.parse_args()

  if len(args) != 1:
    parser.error('must specify a file to upload')
  file_to_upload = args[0]
  if not os.path.exists(file_to_upload):
    die("no such file: %s" % file_to_upload)

  if not opts.domain:
    parser.error('please specify --domain')

  if not opts.site:
    parser.error('please specify --site')

  if not opts.page:
    parser.error("please specify --page")

  if not opts.page.startswith('/'):
    opts.page = '/' + opts.page

  client = GetClient(opts.site, opts.domain, opts.ssl, debug=opts.debug)

  # Find the parent page.
  parent = GetPage(client, opts.page)

  # Make a “media source.”
  ms = gdata.data.MediaSource(file_path=file_to_upload,
                              content_type=opts.content_type)

  # Does it already have an attachment by this name?
  attachment = FindAttachment(client, parent, ms)

  if attachment:
    client.Update(attachment, media_source=ms)
  else:
    attachment = client.UploadAttachment(ms, parent)
  print attachment.GetAlternateLink().href

if __name__ == '__main__':
  main()