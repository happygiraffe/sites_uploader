#!/usr/bin/python
# -*- coding: utf-8 -*-

import gdata.gauth
import gdata.sites.client
import gdata.sites.data
import mox
import unittest

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

if __name__ == '__main__':
  unittest.main()