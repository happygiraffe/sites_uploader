#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Tests for site_uploader.

These are fairly nasty due to the extensive mocking going on.  Suggestions
for improvements would be welcome.
"""

# Third party.
import atom
import atom.data
import gdata.gauth
import gdata.sites.client
import gdata.sites.data
import mox

# Standard.
import StringIO
import os
import re
import tempfile
import unittest

# Mine.
import oneshot
import sites_uploader

DOMAIN = 'example.com'
SITE = 'test'

class StubTokenStore(object):
  def __init__(self, token=None):
    self.token = token

  def ReadToken(self):
    return self.token

  def WriteToken(self, token):
    self.token = token

class ClientAuthorizerTestCase(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def testFetchClientTokenOAuth(self):
    """Horrible.  Simply horrible."""
    token_store = StubTokenStore()
    authz = sites_uploader.ClientAuthorizer(token_store=token_store)
    mock_client = self.mox.CreateMock(gdata.sites.client.SitesClient)
    self.mox.StubOutClassWithMocks(oneshot, 'ParamsReceiverServer')

    # Calls in order…
    mock_httpd = oneshot.ParamsReceiverServer()
    mock_httpd.my_url().AndReturn('http://localhost:54321')
    mock_request_token = self.mox.CreateMock(gdata.gauth.OAuthHmacToken)
    mock_client.GetOAuthToken(sites_uploader.SCOPES, 'http://localhost:54321',
                              'anonymous', 'anonymous').AndReturn(mock_request_token)
    mock_request_token.generate_authorization_url(google_apps_domain=mock_client.domain)
    mock_httpd.serve_until_result()
    mock_httpd.result = '/path?token=12345'
    mock_client.GetAccessToken(mock_request_token).AndReturn('12345')
    self.mox.ReplayAll()

    authz.FetchClientToken(mock_client)

    self.mox.VerifyAll()
    # TODO: use a real token object.
    self.assertEquals(mock_client.auth_token, '12345')

  def testFetchClientTokenStored(self):
    token_store = StubTokenStore('12345')
    mock_client = self.mox.CreateMock(gdata.sites.client.SitesClient)

    authz = sites_uploader.ClientAuthorizer(token_store=token_store)
    authz.FetchClientToken(mock_client)
    # TODO: use a real token object.
    self.assertEquals(mock_client.auth_token, '12345')


# A few helpers to construct gdata objects.
def MakeAttachment(href):
  alt_link = atom.data.Link(rel='alternate', href=href)
  return gdata.sites.data.ContentEntry(kind='attachment', link=[alt_link])


def MakePage(href):
  alt_link = atom.data.Link(rel='alternate', href=href)
  return gdata.sites.data.ContentEntry(id=atom.data.Id(href), link=[alt_link])


def MakeMediaSource(name, contents):
  return gdata.data.MediaSource(file_handle=StringIO.StringIO(contents),
                                content_length=len(contents),
                                file_name=name)


class StubSitesClient(object):
  """A stubbed out gdata.sites.client.SitesClient.

  This is just enough of an implementation to allow me to get the tests to
  run.
  """

  def __init__(self, attachment_feed=None):
    """Construct a new StubSitesClient.

    Args:
      attachment_feed: A gdata.sites.ContentFeed for the attachments of
          a page.
    """
    self.attachment_feed = attachment_feed or gdata.sites.data.ContentFeed()

  def _Base(self):
    return 'http://' + DOMAIN

  def _MakePageFeed(self, path):
    """Make a feed with a single entry (a page)."""
    href = self._Base() + path
    return gdata.sites.data.ContentFeed(entry=[MakePage(href)])

  def MakeContentFeedUri(self):
    return self._Base() + '/feed'

  def GetContentFeed(self, uri):
    # If it looks like we're being asked for a page, give one.
    m = re.search(r'\bpath=([^&#]+)', uri)
    if m:
      if m.group(1) == '/nonexistent':
        # 404
        return gdata.sites.data.ContentFeed()
      else:
        return self._MakePageFeed(m.group(1))
    else:
      return self.attachment_feed

  def UploadAttachment(self, media_source, parent):
    href = parent.GetAlternateLink().href + '/' + media_source.file_name
    return MakeAttachment(href)

  def Update(self, attachment, media_source):
    pass


class SitesUploaderTest(unittest.TestCase):

  def testMakeClient(self):
    class StubClientAuthorizer(object):
      def FetchClientToken(self, client):
        client.auth_token = 'abc12345'

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    client = uploader._MakeClient(StubClientAuthorizer())

    self.assertEquals(DOMAIN, client.domain)
    self.assertEquals(SITE, client.site)
    self.assertEquals(True, client.ssl)
    self.assertEquals('abc12345', client.auth_token)

  def testGetPage(self):
    stub_client = StubSitesClient()
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    entry = uploader._GetPage(stub_client, '/foo')
    self.assertEquals('http://example.com/foo', entry.GetAlternateLink().href)

  def testGetPageForNonexistentPage(self):
    stub_client = StubSitesClient()
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    self.assertRaises(sites_uploader.Error,
                      uploader._GetPage, stub_client, '/nonexistent')

  def testFindAttachmentWhenNotPresent(self):
    stub_client = StubSitesClient()

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    attachment = uploader._FindAttachment(stub_client,
                                          MakePage('http://example.com/42'),
                                          MakeMediaSource('foo.txt', 'foo\n'))

    self.assertEquals(None, attachment)

  def testFindAttachmentWhenPresent(self):
    # “Real” objects to play with.
    existing_attachment = MakeAttachment('http://example.com/foo.txt')
    feed = gdata.sites.data.ContentFeed(entry=[existing_attachment])

    stub_client = StubSitesClient(attachment_feed=feed)
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    attachment = uploader._FindAttachment(stub_client,
                                          MakePage('http://example.com/42'),
                                          MakeMediaSource('foo.txt', 'foo\n'))

    self.assertTrue(existing_attachment is attachment,
                    '%s is not %s' % (attachment, existing_attachment))

  def testUploadFileNotAlreadyPresent(self):
    to_upload = MakeMediaSource('foo.txt', 'foo\n')

    stub_client = StubSitesClient()
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE, client=stub_client)
    result = uploader.UploadFile('/files', to_upload)

    self.assertEquals('http://example.com/files/foo.txt',
                      result.GetAlternateLink().href)

  def testUploadFileOverwritesExisting(self):
    to_upload = MakeMediaSource('foo.txt', 'foo\n')
    attachment = MakeAttachment('http://example.com/files/foo.txt')
    attachment_feed = gdata.sites.data.ContentFeed(entry=[attachment])

    stub_client = StubSitesClient(attachment_feed=attachment_feed)
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE, client=stub_client)
    result = uploader.UploadFile('/files', to_upload)

    self.assertEquals('http://example.com/files/foo.txt',
                      result.GetAlternateLink().href)


if __name__ == '__main__':
  unittest.main()