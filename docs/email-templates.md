# Supabase email templates (required)

Streamlit cannot read the `#access_token=...` fragment that Supabase puts in default email links.
These templates use the documented `token_hash` method instead, which Streamlit *can* read.

Supabase Dashboard -> **Authentication -> Email Templates**. Replace the link in each template:

**Confirm signup**
```html
<h2>Confirm your email</h2>
<p><a href="{{ .SiteURL }}/?token_hash={{ .TokenHash }}&type=signup">Confirm my email</a></p>
```

**Reset password**
```html
<h2>Reset your password</h2>
<p><a href="{{ .SiteURL }}/?token_hash={{ .TokenHash }}&type=recovery">Choose a new password</a></p>
```

Then set **Authentication -> URL Configuration**:
* **Site URL** = your app URL (`http://localhost:8501` locally, your `https://...streamlit.app` URL when deployed)
* **Redirect URLs** = add both URLs above.

Note: the built-in Supabase mailer is limited to a few emails per hour. For a real public launch, add a custom SMTP
provider (Authentication -> SMTP Settings), e.g. Resend, Brevo or Amazon SES.
