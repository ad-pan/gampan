"""Construct concrete SOAP / REST clients (lazy imports to keep optional deps optional)."""

from __future__ import annotations

from google.ads.admanager_v1 import CreativeTemplateServiceClient as AdManagerServiceClient
from googleads import oauth2 as googleads_oauth2
from googleads.ad_manager import AdManagerClient

from gampan.gam.auth import Credentials
from gampan.gam.clients.rest import CreativeTemplateRestClient
from gampan.gam.clients.soap import NativeStyleSoapClient


def soap_client_factory(network_code: str, creds: Credentials) -> NativeStyleSoapClient:
    """Build a SOAP-based NativeStyleSoapClient authorised with *creds*.

    Wraps the resolved ``google.oauth2`` credential in a
    ``googleads.oauth2.GoogleCredentialsClient`` so that the ``googleads``
    library uses the user's actual auth rather than looking up ADC on its own.
    """
    google_creds = creds.to_google_credentials()
    oauth2_client = googleads_oauth2.GoogleCredentialsClient(google_creds)
    am = AdManagerClient(
        oauth2_client=oauth2_client,
        application_name="gampan/0.1.0",
        network_code=network_code,
    )
    svc = am.GetService("NativeStyleService", version="v202508")
    return NativeStyleSoapClient(svc)


def rest_client_factory(network_code: str, creds: Credentials) -> CreativeTemplateRestClient:
    """Build a REST-based CreativeTemplateRestClient authorised with *creds*.

    Passes the resolved ``google.auth.credentials.Credentials`` directly to
    ``AdManagerServiceClient`` so it does not fall back to ADC.
    """
    google_creds = creds.to_google_credentials()
    svc = AdManagerServiceClient(credentials=google_creds)  # type: ignore[arg-type]
    return CreativeTemplateRestClient(svc, network_path=f"networks/{network_code}")
