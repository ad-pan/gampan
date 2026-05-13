"""Construct concrete SOAP / REST clients (lazy imports to keep optional deps optional)."""

from __future__ import annotations

from google.ads.admanager_v1 import CreativeTemplateServiceClient as AdManagerServiceClient
from googleads.ad_manager import AdManagerClient

from gampan.gam.clients.rest import CreativeTemplateRestClient
from gampan.gam.clients.soap import NativeStyleSoapClient


def soap_client_factory(network_code: str) -> NativeStyleSoapClient:
    yaml_cfg = f"ad_manager:\n  application_name: gampan/0.1.0\n  network_code: {network_code}\n"
    am = AdManagerClient.LoadFromString(yaml_cfg)
    svc = am.GetService("NativeStyleService", version="v202508")
    return NativeStyleSoapClient(svc)


def rest_client_factory(network_code: str) -> CreativeTemplateRestClient:
    svc = AdManagerServiceClient()
    return CreativeTemplateRestClient(svc, network_path=f"networks/{network_code}")
