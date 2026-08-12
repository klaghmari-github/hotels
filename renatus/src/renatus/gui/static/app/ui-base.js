/**
 * UiController — base mount/render pour les controleurs UI GUI (F0053-S4).
 */

/**
 * Controleur UI generique : cycle mount → render → unmount.
 * Les classes GraphCanvas / Toolbox / PipelineTabs (et S6 ConfigPanel)
 * heritent de ce pattern.
 */
export class UiController {
  /**
   * @param {Element|null} [root] element racine optionnel
   */
  constructor(root) {
    this.root = root || null;
    this.mounted = false;
  }

  /**
   * Attache le controleur a un element DOM.
   * @param {Element|null} [root]
   * @returns {this}
   */
  mount(root) {
    if (root != null) this.root = root;
    this.mounted = true;
    this.onMount();
    return this;
  }

  /**
   * Detache le controleur.
   * @returns {this}
   */
  unmount() {
    this.onUnmount();
    this.mounted = false;
    return this;
  }

  /** Hook apres mount — a surcharger. */
  onMount() {}

  /** Hook avant unmount — a surcharger. */
  onUnmount() {}

  /**
   * Redessine la vue — a surcharger.
   * @returns {this}
   */
  render() {
    return this;
  }
}
