# Red Energy API Authentication Guide

This guide explains how to authenticate with the Red Energy API and obtain the required credentials for the Home Assistant integration.

## Overview

The Red Energy API uses OAuth2 PKCE (Proof Key for Code Exchange) authentication flow with Okta as the identity provider. This ensures secure authentication while protecting user credentials.

## Authentication Flow

The integration implements the following authentication sequence:

1. **Username/Password Authentication** → Okta session token
2. **Session Token** → OAuth2 authorization URL with PKCE challenge
3. **Authorization Redirect** → Extract authorization code
4. **Authorization Code + PKCE Verifier** → Access/Refresh tokens
5. **Access Token** → API calls with Bearer authentication

## Required Credentials

### 1. Username & Password
- Your Red Energy account email address and password
- These are the same credentials you use to log into the Red Energy website/app

### 2. Client ID
The Client ID is a unique identifier for the Red Energy mobile application. You must capture this from the mobile app's network traffic.

#### How to Obtain Client ID

**Option 1: Using Proxyman (Mac)**

1. Download and install [Proxyman](https://proxyman.io/)
2. Open Proxyman and start capturing
3. Configure your mobile device to use Proxyman as a proxy:
   - iOS: Settings → Wi-Fi → Your Network → Configure Proxy → Manual
   - Set server to your Mac's IP address and port 9090
4. Install the Proxyman certificate on your device (follow Proxyman's guide)
5. Open the Red Energy mobile app and log in
6. In Proxyman, look for requests to:
   - `redenergy.okta.com`
   - `login.redenergy.com.au`
7. Find OAuth2 requests and locate the `client_id` parameter
8. Copy this value for use in the integration

**Option 2: Using Charles Proxy**

1. Download and install [Charles Proxy](https://www.charlesproxy.com/)
2. Configure your mobile device to use Charles as a proxy
3. Install SSL certificates for HTTPS decryption
4. Capture traffic while using the Red Energy app
5. Look for the `client_id` in OAuth2 requests

**Example Client ID Format:**
```
0oa1a2b3c4d5e6f7g8h9
```

## API Endpoints

The integration uses these Red Energy API endpoints:

- **Discovery**: `https://login.redenergy.com.au/oauth2/default/.well-known/openid-configuration`
- **Okta Auth**: `https://redenergy.okta.com/api/v1/authn`
- **Base API**: `https://selfservice.services.retail.energy/v1`
- **Customer Data**: `/customers/current`
- **Properties**: `/properties`
- **Usage Data**: `/usage/interval`

## Security Considerations

- **Client ID**: This is specific to the Red Energy mobile app and should not be shared publicly
- **Credentials**: Your username/password are only used locally and not stored permanently
- **Tokens**: Access tokens are refreshed automatically and stored securely in Home Assistant
- **HTTPS**: All communications use encrypted HTTPS connections

## Troubleshooting

### Authentication Errors

- **"Authentication failed"**: Verify your username/password are correct
- **"Invalid client ID"**: Ensure you captured the client_id correctly from the mobile app
- **"Authorization failed"**: The OAuth2 flow may have failed - check network connectivity

### Network Issues

- **Timeout errors**: Red Energy's servers may be temporarily unavailable
- **SSL/TLS errors**: Check your Home Assistant's SSL configuration

### Token Refresh

- Access tokens expire after 1 hour and are automatically refreshed
- If refresh fails, re-authentication will be attempted automatically
- Persistent token refresh failures may require re-entering credentials

## Testing Authentication

To test your credentials before configuring the integration:

1. Use the Red Energy mobile app to verify your username/password work
2. Check that your captured client_id is valid by attempting integration setup
3. Monitor Home Assistant logs for detailed authentication error messages

## Reference Implementation

This authentication flow is based on the patterns used in the [Red-Energy-API](https://github.com/craibo/Red-Energy-API) project, adapted for asynchronous Home Assistant integration requirements.

## Support

If you encounter issues with authentication:

1. Check Home Assistant logs for detailed error messages
2. Verify your credentials work in the Red Energy mobile app
3. Re-capture the client_id if authentication continues to fail
4. Report persistent issues via [GitHub Issues](https://github.com/craibo/ha-red-energy-au/issues)