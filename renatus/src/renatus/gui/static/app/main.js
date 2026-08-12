/**
 * Entry Renatus GUI (F0053-S2 / F0053-S4) — modules ES natifs, sans bundler.
 * GuiApp possede le bootstrap; startGui reste disponible.
 */
import { GuiApp, startGuiApp } from "./gui-app.js";

const app = startGuiApp();

export { GuiApp, app };
