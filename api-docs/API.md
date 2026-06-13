# Nectr API Quick Overview

Nectr uses GraphQL and all API "calls" we make utilise the same GraphQL endpoint. There are 2 calls we'll make:

- login
- get hourly electricity usage for a day

Before requesting hourly usage data, login must be called to get a new bearer token. We don't make a logout call as it appears to be unnecessary as we're only going to be requesting data once a day.

## Login
Refer to the "login.har" file in this folder to see the structure of the request and response. The "token" value in the response is the value to use for the "Authorization" header bearer token on electricity usage requests.

## Usage
Refer to the "day-usage.har" file in this folder to see the structure of the request and response. Ensure an "Authorization" header is present, with a value of "bearer {{token-from-login}}". Data appears in the response in descending order (11pm, 10pm, 9pm etc.)