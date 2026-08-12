"""Page /admin/login — formulaire de connexion admin."""

LOGIN_CSS = """
.login-wrap {
  max-width: 420px; margin: 2.5rem auto 2rem; padding: 0 1rem;
}
.login-card {
  border: 1px solid var(--line);
  border-radius: 16px;
  background: linear-gradient(165deg, #121a24 0%, #0e1520 100%);
  padding: 1.5rem 1.4rem 1.35rem;
  box-shadow: 0 12px 40px rgba(0,0,0,.25);
}
.login-card h2 {
  margin: 0 0 .35rem; font-size: 1.25rem;
}
.login-card .sub {
  color: var(--muted); font-size: .9rem; margin: 0 0 1.15rem;
}
.login-field { margin: 0 0 .85rem; }
.login-field label {
  display: block; font-size: .72rem; text-transform: uppercase;
  letter-spacing: .04em; color: var(--muted); font-weight: 700; margin: 0 0 .35rem;
}
.login-field input {
  width: 100%; box-sizing: border-box;
  padding: .65rem .75rem; border-radius: 10px;
  border: 1px solid var(--line); background: #101820; color: var(--text);
  font-size: 1rem;
}
.login-field input:focus {
  outline: none; border-color: var(--accent);
}
.login-error {
  margin: 0 0 .85rem; padding: .6rem .75rem; border-radius: 10px;
  border: 1px solid #5a2a35; background: #2a1520; color: #f5a0b0;
  font-size: .9rem;
}
.login-actions {
  display: flex; gap: .5rem; flex-wrap: wrap;
  justify-content: space-between; align-items: center; margin-top: 1.1rem;
}
.login-actions .btn.primary { min-width: 8rem; }
"""

LOGIN_BODY = """
<div class="login-wrap">
  <div class="login-card">
    <h2>Connexion admin</h2>
    <p class="sub">Studio donnees</p>
    __ERROR__
    <form method="post" action="/admin/login" autocomplete="on">
      <input type="hidden" name="next" value="__NEXT__"/>
      <div class="login-field">
        <label for="username">Identifiant</label>
        <input id="username" name="username" type="text" required
          autocomplete="username" autofocus value="__USERNAME__"/>
      </div>
      <div class="login-field">
        <label for="password">Mot de passe</label>
        <input id="password" name="password" type="password" required
          autocomplete="current-password"/>
      </div>
      <div class="login-actions">
        <a class="btn" href="/">Retour accueil</a>
        <button class="btn primary" type="submit">Se connecter</button>
      </div>
    </form>
  </div>
</div>
"""


def render_login_body(*, error: str = "", next_url: str = "/admin", username: str = "") -> str:
    err_html = f'<div class="login-error">{error}</div>' if error else ""
    # escape minimal pour attributs / texte
    def esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    return (
        LOGIN_BODY.replace("__ERROR__", err_html)
        .replace("__NEXT__", esc(next_url or "/admin"))
        .replace("__USERNAME__", esc(username or ""))
    )
