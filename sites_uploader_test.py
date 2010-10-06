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
    alt_link = atom.data.Link(rel='alternate', href=href)
    page = gdata.sites.data.ContentEntry(id=atom.data.Id(href), link=[alt_link])
    return gdata.sites.data.ContentFeed(entry=[page])

  def _MakeAttachment(self, href):
    alt_link = atom.data.Link(rel='alternate', href=href)
    return gdata.sites.data.ContentEntry(kind='attachment', link=[alt_link])

  def MakeContentFeedUri(self):
    return self._Base() + '/feed'

  def GetContentFeed(self, uri):
    # If it looks like we're being asked for a page, give one.
    m = re.search(r'\bpath=([^&#]+)', uri)
    if m:
      return self._MakePageFeed(m.group(1))
    else:
      return self.attachment_feed

  def UploadAttachment(self, media_source, parent):
    href = parent.GetAlternateLink().href + '/' + media_source.file_name
    return self._MakeAttachment(href)

  def Update(self, attachment, media_source):
    pass


class SitesUploaderTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def testMakeClient(self):
    mock_authz = self.mox.CreateMock(sites_uploader.ClientAuthorizer)
    mock_authz.FetchClientToken(mox.IsA(gdata.sites.client.SitesClient))
    self.mox.ReplayAll()

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    client = uploader._MakeClient(mock_authz)

    self.mox.VerifyAll()
    self.assertEquals(DOMAIN, client.domain)
    self.assertEquals(SITE, client.site)
    self.assertEquals(True, client.ssl)

  def _MockGetPage(self, *entries):
    mock_client = self.mox.CreateMock(gdata.sites.client.SitesClient)
    mock_client.MakeContentFeedUri().AndReturn('http://example.com/feed')
    mock_content_feed = self.mox.CreateMock(gdata.sites.data.ContentFeed)
    mock_content_feed.entry = entries
    mock_client.GetContentFeed('http://example.com/feed?path=/foo').AndReturn(mock_content_feed)
    return mock_client

  def testGetPage(self):
    mock_client = self._MockGetPage('ContentEntry object')
    self.mox.ReplayAll()

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    entry = uploader._GetPage(mock_client, '/foo')
    self.mox.VerifyAll()
    self.assertEquals('ContentEntry object', entry)

  def testGetPageForNonexistentPage(self):
    mock_client = self._MockGetPage()
    self.mox.ReplayAll()

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    self.assertRaises(sites_uploader.Error, uploader._GetPage, mock_client, '/foo')
    self.mox.VerifyAll()

  def SomePage(self):
    page = gdata.sites.data.ContentEntry()
    page.id = atom.Id('http://example.com/42')
    return page

  def MockClientForGetAttachment(self, feed):
    mock_client = self.mox.CreateMock(gdata.sites.client.SitesClient)
    mock_client.MakeContentFeedUri().AndReturn('http://example.com')
    mock_client.GetContentFeed(
        'http://example.com?parent=42&kind=attachment').AndReturn(feed)
    return mock_client

  def testFindAttachmentWhenNotPresent(self):
    # “Real” objects to play with.
    page = self.SomePage()
    media_source = gdata.data.MediaSource(file_name='foo.txt')
    feed = gdata.sites.data.ContentFeed()

    # Mock objects.
    mock_client = self.MockClientForGetAttachment(feed)
    self.mox.ReplayAll()

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    attachment = uploader._FindAttachment(mock_client, page, media_source)

    self.mox.VerifyAll()
    self.assertEquals(None, attachment)

  def testFindAttachmentWhenPresent(self):
    # “Real” objects to play with.
    page = self.SomePage()
    media_source = gdata.data.MediaSource(file_name='foo.txt')

    alt_link = atom.data.Link(rel='alternate', href='http://example.com/foo.txt')
    existing_attachment = gdata.sites.data.ContentEntry(kind='attachment',
                                                        link=[alt_link])
    feed = gdata.sites.data.ContentFeed(entry=[existing_attachment])

    # Mock objects.
    mock_client = self.MockClientForGetAttachment(feed)
    self.mox.ReplayAll()

    uploader = sites_uploader.SitesUploader(DOMAIN, SITE)
    attachment = uploader._FindAttachment(mock_client, page, media_source)

    self.mox.VerifyAll()
    self.assertTrue(existing_attachment is attachment,
                    '%s is not %s' % (attachment, existing_attachment))

  def MakeAttachment(self, href):
    alt_link = atom.data.Link(rel='alternate', href=href)
    return gdata.sites.data.ContentEntry(kind='attachment', link=[alt_link])

  def MakeMediaSource(self, name, contents):
    return gdata.data.MediaSource(file_handle=StringIO.StringIO(contents),
                                       content_length=len(contents),
                                       file_name=name)

  def testUploadFileNotAlreadyPresent(self):
    to_upload = self.MakeMediaSource('foo.txt', 'foo\n')

    stub_client = StubSitesClient()
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE, client=stub_client)
    result = uploader.UploadFile('/files', to_upload)

    self.assertEquals('http://example.com/files/foo.txt',
                      result.GetAlternateLink().href)

  def testUploadFileOverwritesExisting(self):
    to_upload = self.MakeMediaSource('foo.txt', 'foo\n')
    attachment = self.MakeAttachment('http://example.com/files/foo.txt')
    attachment_feed = gdata.sites.data.ContentFeed(entry=[attachment])

    stub_client = StubSitesClient(attachment_feed=attachment_feed)
    uploader = sites_uploader.SitesUploader(DOMAIN, SITE, client=stub_client)
    result = uploader.UploadFile('/files', to_upload)

    self.assertTrue(result is attachment)


if __name__ == '__main__':
  unittest.main()