# Nectr API Quick Overview

Nectr uses GraphQL and all API requests we make utilise the same GraphQL endpoint. There are 3 requests we'll make:

- login
- get accounts
- get hourly electricity usage on a day for an account

Before requesting usage data, login must be called to get a new bearer token, and we must get a list of accounts the user has with Nectr. Requesting usage requires an active bearer token as well as an account number. We don't make a logout call as it appears to be unnecessary as we're only going to be requesting data once a day.

## Login
Refer to the "emailAuthenticate.har" file in this folder to see the structure of the "emailAuthenticate" request and response. The "token" value in the response is the value to use for the "Authorization" header bearer token on all other requests.

## Accounts
Refer to the "getUserBrief.har" file in this folder to see the structure of the "getUserBrief" request and response. The "accounts" array in the "userBrief" object of the response contains a list of accounts the user has with Nectr. The "number" field in an account object is used when requesting usage data.

## Usage
Refer to the "getUsageInfo.har" file in this folder to see the structure of the "getUsageInfo" request and response. Ensure an "Authorization" header is present, with a value of "bearer {{token-from-login}}". Data appears in the response in descending order (11pm, 10pm, 9pm etc.)