// ============================================================
//  Safari POS Pro - Auth Manager
//  Token stored in sessionStorage (cleared on logout/close)
// ============================================================

const API_BASE_URL = "/api/v1";

class AuthManager {
    constructor() {
        this.token = sessionStorage.getItem("safari_pos_token");
        this.user = JSON.parse(sessionStorage.getItem("safari_pos_user") || "null");
    }

    async login(identifier, password) {
        const response = await fetch(API_BASE_URL + "/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: identifier, password: password })
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: "Login failed" }));
            throw new Error(error.detail || "Login failed");
        }

        const data = await response.json();
        this.token = data.access_token;
        this.user = data.user;

        sessionStorage.setItem("safari_pos_token", this.token);
        sessionStorage.setItem("safari_pos_user", JSON.stringify(this.user));

        return data;
    }

    logout() {
        this.token = null;
        this.user = null;
        sessionStorage.clear();
        localStorage.clear();

        // Clear cookies
        document.cookie.split(";").forEach(function (c) {
            document.cookie = c
                .replace(/^ +/, "")
                .replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
        });

        window.location.href = "/login";
    }

    isAuthenticated() {
        return !!this.token;
    }

    getAuthHeaders() {
        return {
            "Authorization": "Bearer " + this.token,
            "Content-Type": "application/json"
        };
    }

    getUser() {
        return this.user;
    }
}

const authManager = new AuthManager();
