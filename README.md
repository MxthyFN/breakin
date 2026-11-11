# breakin — local login test target

A self-contained, single-page login/signup form used as a **test target** for a
password/credential tool. It is intentionally simple so you can create many
username/password combinations and exercise your tool against them.

## What it does

- `index.html` — a generic banking-style login page (no real brand, no
  copyrighted assets).
- **Sign In** and **Open Account** (signup) tabs.
- Accounts are stored in the browser's `localStorage` under the key
  `ngst_accounts`. `localStorage` is scoped by the browser to this page's
  origin, so credentials created here live only with this site and are not
  shared with any other site.
- Login compares the entered password against the stored one and, on success,
  shows a mock account dashboard. A session flag is kept under `ngst_session`.

## Usage

Open `index.html` in a browser (or serve the folder):

```bash
python3 -m http.server 8000
```

Then visit http://localhost:8000 . Use **Open Account** to register as many
test credential pairs as you want, then test your tool against the **Sign In**
form.

## Reset

Clear the stored accounts from the browser console:

```js
localStorage.removeItem("ngst_accounts");
localStorage.removeItem("ngst_session");
```
