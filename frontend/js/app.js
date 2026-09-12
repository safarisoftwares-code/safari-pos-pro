// ============================================================
//  Safari POS Pro - App bootstrap
//  Runs on page load: auth check, user info, logout wiring
// ============================================================

class App {
    constructor() {
        this.init();
    }

    init() {
        this.checkAuth();
        this.setupLogout();
        this.loadUserInfo();
    }

    checkAuth() {
        if (!authManager.isAuthenticated()) {
            sessionStorage.clear();
            localStorage.clear();
            window.location.href = "/login";
        }
    }

    loadUserInfo() {
        const user = authManager.getUser();
        if (user) {
            const nameEl = document.getElementById("userName");
            const roleEl = document.getElementById("userRole");
            if (nameEl) nameEl.textContent = user.name;
            if (roleEl) roleEl.textContent = (user.role || "").toUpperCase();
        }
    }

    setupLogout() {
        const btn = document.getElementById("logoutBtn");
        if (!btn) return;
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            if (confirm("Logout?")) {
                authManager.logout();
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.app = new App();
});
