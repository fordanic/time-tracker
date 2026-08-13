import { render } from "preact";
import { App } from "./App.tsx";
import "./styles.css";

const appearance = localStorage.getItem("time-tracker-appearance");
document.documentElement.dataset.appearance =
  appearance === "light" || appearance === "dark" ? appearance : "system";

const root = document.querySelector<HTMLDivElement>("#app");
if (!root) throw new Error("App mount point is missing");
render(<App />, root);
