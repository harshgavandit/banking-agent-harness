# Banking Agent Harness

A banking demo where you can check an account, find saved beneficiaries, and make simulated transfers through a chat assistant.

[Open the app](https://banking-agent-harness.vercel.app)

## What you can do

- Check your savings balance, daily transfer limit, and how much of that limit you have used.
- Find a saved beneficiary by name, ID, or the last four digits of their account.
- Request a transfer and review the recipient, account ending, and amount before confirming it.
- Check the status of a transfer using its transaction ID.

The app checks the account balance, transfer limit, amount, and beneficiary status before staging a transfer. If a name matches more than one beneficiary, it asks you to choose. Transfers to blocked beneficiaries are rejected.

A valid transfer stays pending until you confirm it in a separate message or use the **Confirm transfer** button. The result is shown as successful, failed, or pending. Successful and pending transfers reduce the available demo balance; failed transfers leave it unchanged.

## Try it

```text
What is my savings account balance?
Transfer 1000 rupees to Aaron.
confirm
Check transaction TXN001.
```

Each visitor gets a separate demo account and chat history. Your conversation and account state are saved between requests, so you can return to a pending transfer after refreshing the page.

All accounts, beneficiaries, and transactions use mock data. No real money moves.
