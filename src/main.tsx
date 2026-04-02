import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { CognitoAuthProvider } from "./adapters/cognito-auth-provider";
import App from "./App";
import "./styles/globals.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <CognitoAuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </CognitoAuthProvider>
  </React.StrictMode>
);
