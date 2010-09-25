#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Upload an attachment to a sites page."""

import getpass
import optparse
import os
import sys

import gdata.data
import gdata.gauth
import gdata.sites.client
import gdata.sites.data

import oneshot

VERSION = '1.0'
SOURCE = 'Dom-SitesUploader-%s' % VERSION

# OAuth bits.  We use “anonymous” to behave as an unregistered  application.
# Maybe I'll register later on if I figure this stuff out…
CONSUMER_KEY = 'anonymous'
CONSUMER_SECRET = 'anonymous'
# TODO: limit scope to just what we actually need.
SCOPES = ['http://sites.google.com/feeds/',
          'https://sites.google.com/feeds/']

def die(msg):
  me = os.path.basename(sys.argv[0])
  print >>sys.stderr, me + ": " + msg
  sys.exit(1)

def TokenFile():
  """Return the token file."""
  me = os.path.basename(sys.argv[0])
  return os.path.expanduser('~/.%s.tok' % me)

def ReadToken():
  """Read in the stored auth token."""
  if os.path.exists(TokenFile()):
    return open(TokenFile()).readline().rstrip()
  else:
    return None

def WriteToken(tok):
  """Write token to a file."""
  path = TokenFile()
  fh = open(path, 'w')
  os.chmod(path, 0600)
  fh.write(tok)
  fh.write('\n')
  fh.close()

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

def FetchClientToken(client):
  """Ensure client has a valid token."""
  token = ReadToken()
  if token:
    (token, token_secret) = token.split(':')
    access_token = gdata.gauth.OAuthHmacToken(CONSUMER_KEY, CONSUMER_SECRET,
                                              token, token_secret,
                                              gdata.gauth.ACCESS_TOKEN)
  else:
    httpd = oneshot.ParamsReceiverServer()
    # TODO Find a way to pass "xoauth_displayname" parameter.
    request_token = client.GetOAuthToken(
        SCOPES, httpd.my_url(), CONSUMER_KEY, consumer_secret=CONSUMER_SECRET)
    url = request_token.generate_authorization_url(google_apps_domain=client.domain)
    print 'Please visit this URL to continue authorization:'
    print url
    httpd.serve_until_result()
    request_token = gdata.gauth.AuthorizeRequestToken(request_token, httpd.result)
    access_token = client.GetAccessToken(request_token)
    # Have to serialize the access_token (a gdata.gauth.OAuthHmacToken).
    # It would be nicer to pickle perhaps?
    WriteToken(':'.join([access_token.token, access_token.token_secret]))
  client.auth_token = access_token

def GetClient(site, domain, ssl, debug=False):
  """Return a populated SitesClient object."""
  client = gdata.sites.client.SitesClient(source=SOURCE, site=site,
                                          domain=domain)
  client.ssl = ssl
  client.http_client.debug = debug
  FetchClientToken(client)
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