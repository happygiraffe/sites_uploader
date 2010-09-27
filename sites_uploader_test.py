#!/usr/bin/python

import gdata.sites.client
import mox
import unittest

import sites_uploader

class SitesUploaderTest(unittest.TestCase):
  
  DOMAIN = 'example.com'
  SITE = 'test'
  
  def setUp(self):
    self.mox = mox.Mox()
  
  def tearDown(self):
    self.mox.UnsetStubs()
  
  def testMakeClient(self):
    mock_authz = self.mox.CreateMock(sites_uploader.ClientAuthorizer)
    mock_authz.FetchClientToken(mox.IsA(gdata.sites.client.SitesClient))
    self.mox.ReplayAll()

    uploader = sites_uploader.SitesUploader(self.DOMAIN, self.SITE)
    client = uploader._MakeClient(mock_authz)

    self.mox.VerifyAll()
    self.assertEquals(self.DOMAIN, client.domain)
    self.assertEquals(self.SITE, client.site)
    self.assertEquals(True, client.ssl)

if __name__ == '__main__':
  unittest.main()