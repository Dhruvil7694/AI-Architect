"use client";

import { useState } from "react";

export default function TestLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [clicked, setClicked] = useState(false);

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: "#f5f5f5",
      padding: "20px"
    }}>
      <div style={{
        width: "100%",
        maxWidth: "400px",
        backgroundColor: "white",
        padding: "40px",
        borderRadius: "8px",
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        position: "relative",
        zIndex: 99999
      }}>
        <h1 style={{ marginBottom: "10px", fontSize: "24px", fontWeight: "600" }}>
          Test Login Page
        </h1>
        <p style={{ marginBottom: "30px", fontSize: "14px", color: "#666" }}>
          If you can interact with this page, the issue is with the main login page
        </p>

        <form onSubmit={(e) => {
          e.preventDefault();
          alert(`Email: ${email}, Password: ${password}`);
          setClicked(true);
        }}>
          <div style={{ marginBottom: "20px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onClick={() => setClicked(true)}
              style={{
                width: "100%",
                padding: "10px",
                border: "1px solid #ccc",
                borderRadius: "4px",
                fontSize: "14px",
                position: "relative",
                zIndex: 99999
              }}
              placeholder="test@example.com"
            />
          </div>

          <div style={{ marginBottom: "20px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onClick={() => setClicked(true)}
              style={{
                width: "100%",
                padding: "10px",
                border: "1px solid #ccc",
                borderRadius: "4px",
                fontSize: "14px",
                position: "relative",
                zIndex: 99999
              }}
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            onClick={() => setClicked(true)}
            style={{
              width: "100%",
              padding: "12px",
              backgroundColor: "#000",
              color: "white",
              border: "none",
              borderRadius: "4px",
              fontSize: "14px",
              cursor: "pointer",
              position: "relative",
              zIndex: 99999
            }}
          >
            Test Submit
          </button>
        </form>

        {clicked && (
          <div style={{
            marginTop: "20px",
            padding: "10px",
            backgroundColor: "#d4edda",
            border: "1px solid #c3e6cb",
            borderRadius: "4px",
            color: "#155724"
          }}>
            ✓ Click detected! Elements are working.
          </div>
        )}

        <div style={{ marginTop: "20px", fontSize: "12px", color: "#999" }}>
          <p>Email value: {email || "(empty)"}</p>
          <p>Password value: {password ? "•".repeat(password.length) : "(empty)"}</p>
          <p>Clicked: {clicked ? "Yes" : "No"}</p>
        </div>
      </div>
    </div>
  );
}
