/* The renderer's entry: mount the app. Everything else lives in App and the modules under it. */

import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<App />);
