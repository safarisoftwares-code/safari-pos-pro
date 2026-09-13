// ============================================================
//  Safari POS Pro - main.js
//  Part 1: Foundation (state, navigation, modals, helpers)
// ============================================================

// ---------- State ----------
let products = [];
let categories = [];
let cart = [];
let discount = 0;
let businessSettings = null;


// ============================================================
//  Safe helpers
// ============================================================

function safeOn(id, event, handler) {
    const el = document.getElementById(id);
    if (el) el.addEventListener(event, handler);
}

function singleSubmit(handler) {
    let running = false;
    return async function (event) {
        if (event) event.preventDefault();
        if (running) return;
        running = true;
        try {
            await handler(event);
        } catch (err) {
            showError(err);
        } finally {
            running = false;
        }
    };
}

function showError(err) {
    const msg = (err && err.message) ? err.message : String(err);
    console.error("[error]", msg);
    alert("Error: " + msg);
}

function showSuccess(msg) {
    console.log("[ok]", msg);
    alert(msg);
}


// ============================================================
//  API caller
// ============================================================

async function apiCall(url, method, data) {
    method = method || "GET";
    const options = {
        method: method,
        headers: authManager.getAuthHeaders(),
    };
    if (data !== undefined && data !== null) {
        options.body = JSON.stringify(data);
    }

    let response;
    try {
        response = await fetch(API_BASE_URL + url, options);
    } catch (networkErr) {
        throw new Error("Cannot reach the server. Is it running?");
    }

    if (!response.ok) {
        let detail = "Request failed (" + response.status + ")";
        try {
            const error = await response.json();
            if (error.detail) detail = error.detail;
        } catch (_) { }
        throw new Error(detail);
    }

    const text = await response.text();
    if (!text) return null;
    try {
        return JSON.parse(text);
    } catch (_) {
        return text;
    }
}


// ============================================================
//  Navigation
// ============================================================

function showView(viewName) {
    const user = authManager.getUser();
    if (user && user.role === "cashier") {
        const allowed = ["dashboard", "pos", "receipts"];
        if (!allowed.includes(viewName)) {
            alert("Access denied.");
            return;
        }
    }

    document.querySelectorAll(".view").forEach(v => (v.style.display = "none"));

    const target = document.getElementById(viewName);
    if (target) target.style.display = "block";

    document.querySelectorAll(".sidebar-menu a").forEach(a => a.classList.remove("active"));

    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.remove("active");

    const loaders = {
        dashboard: () => typeof loadDashboard === "function" && loadDashboard(),
        pos: () => typeof loadProductsForPOS === "function" && loadProductsForPOS(),
        products: () => typeof loadProducts === "function" && loadProducts(),
        categories: () => typeof loadCategories === "function" && loadCategories(),
        users: () => typeof loadUsers === "function" && loadUsers(),
        reports: () => {
            typeof loadAllSales === "function" && loadAllSales();
            typeof loadLowStock === "function" && loadLowStock();
            typeof loadDailyClose === "function" && loadDailyClose();
            typeof loadProfitReport === "function" && loadProfitReport();
        },
        analytics: () => {
            typeof loadAnalytics === "function" && loadAnalytics();
            typeof loadExpiryReport === "function" && loadExpiryReport();
        },
        printQueue: () => {
            typeof loadPrintQueue === "function" && loadPrintQueue();
            typeof startPrintQueueAutoRefresh === "function" && startPrintQueueAutoRefresh();
        },
        tax: () => {
              typeof loadTaxReport === "function" && loadTaxReport();
              typeof loadTaxArchive === "function" && loadTaxArchive();
          },
        receipts: () => typeof loadReceiptHistory === "function" && loadReceiptHistory(),
        purchaseOrders: () => typeof loadPurchaseOrders === "function" && loadPurchaseOrders(),
        settings: () => {
            typeof loadSettings === "function" && loadSettings();
            typeof loadMpesaSettings === "function" && loadMpesaSettings();
            typeof loadExpirySettings === "function" && loadExpirySettings();
            typeof loadPrinterSettings === "function" && loadPrinterSettings();
        },
    };

    if (loaders[viewName]) {
        try {
            loaders[viewName]();
        } catch (err) {
            console.error("[showView:" + viewName + "]", err);
        }
    }
}


// ============================================================
//  Modals
// ============================================================

function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("active");
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("active");
}


// ============================================================
//  Bootstrap
// ============================================================

document.addEventListener("DOMContentLoaded", async () => {
    const user = authManager.getUser();

    if (user && user.role === "cashier") {
        const restricted = ["Products", "Categories", "Users", "Reports", "Analytics", "Tax", "Purchase Orders", "Backup", "Settings"];
        document.querySelectorAll(".sidebar-menu a").forEach(a => {
            if (restricted.includes(a.textContent.trim())) {
                a.style.display = "none";
            }
        });
    }

    try {
        if (typeof loadDashboard === "function") await loadDashboard();
    } catch (err) {
        console.error("[bootstrap:dashboard]", err);
    }

    try {
        if (typeof loadBusinessSettings === "function") await loadBusinessSettings();
        if (!businessSettings) {
            businessSettings = await apiCall("/settings/");
        }
    } catch (err) {
        console.error("[bootstrap:settings]", err);
        businessSettings = {};
    }

    console.log("[Safari POS Pro] Part 1 loaded OK");
});


// ============================================================
//  Safari POS Pro - main.js
//  Part 2: Categories + Products
// ============================================================

// ============================================================
//  Categories
// ============================================================

async function loadCategories() {
    try {
        categories = await apiCall("/products/categories");
        const tbody = document.getElementById("categoriesTableBody");
        if (!tbody) return;

        if (!categories || categories.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"4\">No categories yet</td></tr>";
            return;
        }

        tbody.innerHTML = categories.map(c =>
            "<tr><td>" + c.id + "</td><td>" + c.name + "</td><td>" +
            (c.description || "-") +
            "</td><td><button onclick=\"deleteCategory(" + c.id +
            ")\" style=\"color:red;padding:3px 8px;font-size:11px;cursor:pointer\">Delete</button></td></tr>"
        ).join("");
    } catch (err) {
        showError(err);
    }
}

async function loadCategoriesForSelect() {
    try {
        categories = await apiCall("/products/categories");
    } catch (err) {
        console.error("[loadCategoriesForSelect]", err);
        categories = [];
    }

    const opts = "<option value=\"\">Select Category</option>" +
        categories.map(c => "<option value=\"" + c.id + "\">" + c.name + "</option>").join("");
    const optsEdit = "<option value=\"\">No Category</option>" +
        categories.map(c => "<option value=\"" + c.id + "\">" + c.name + "</option>").join("");
    const optsPos = "<option value=\"all\">All Categories</option>" +
        categories.map(c => "<option value=\"" + c.id + "\">" + c.name + "</option>").join("");

    const sel = document.getElementById("productCategory");
    if (sel) sel.innerHTML = opts;
    const selEdit = document.getElementById("editProductCategory");
    if (selEdit) selEdit.innerHTML = optsEdit;
    const selPos = document.getElementById("posCategoryFilter");
    if (selPos) selPos.innerHTML = optsPos;
}

function openCategoryModal() {
    const nameEl = document.getElementById("categoryName");
    const descEl = document.getElementById("categoryDescription");
    if (nameEl) nameEl.value = "";
    if (descEl) descEl.value = "";
    openModal("categoryModal");
}

async function saveCategory() {
    const name = document.getElementById("categoryName").value.trim();
    const desc = document.getElementById("categoryDescription").value.trim();

    if (!name) {
        alert("Please enter a category name.");
        return;
    }

    try {
        await apiCall("/products/categories", "POST", {
            name: name,
            description: desc || null,
        });
        closeModal("categoryModal");
        showSuccess("Category added!");
        await loadCategories();
    } catch (err) {
        showError(err);
    }
}

async function deleteCategory(id) {
    if (prompt("Type DELETE to confirm:") !== "DELETE") return;
    try {
        await apiCall("/products/categories/" + id, "DELETE");
        showSuccess("Category deleted!");
        await loadCategories();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Products
// ============================================================

async function loadProducts() {
    try {
        await loadCategoriesForSelect();
        products = await apiCall("/products");

        const tbody = document.getElementById("productsTableBody");
        if (!tbody) return;

        if (!products || products.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"8\">No products yet</td></tr>";
            return;
        }

        tbody.innerHTML = products.map(p => {
            const cat = categories.find(c => c.id === p.category_id);
            const taxLabel = (p.tax_rate || 0) > 0 ? "A" : "B";
            return "<tr><td>" + p.id + "</td><td>" + p.name + "</td><td>" +
                (p.unit || "-") + "</td><td>" + (cat ? cat.name : "-") +
                "</td><td>KSh " + p.price + "</td>" +
                "<td style=\"text-align:center;font-weight:bold\">" + taxLabel + "</td>" +
                "<td>" + p.stock + "</td>" +
                "<td style=\"text-align:center;color:#666;font-size:11px\">" + (p.low_stock_alert || 5) + "</td>" +
                "<td>" +
                "<button onclick=\"openEditProductModal(" + p.id + ")\" style=\"padding:5px 10px;font-size:10px;margin-right:3px;background:#2e7d32;color:white;border:none;border-radius:3px;cursor:pointer\">Edit</button>" +
                "<button onclick=\"openStockModal(" + p.id + ")\" style=\"padding:5px 10px;font-size:10px;margin-right:3px;cursor:pointer\">Stock</button>" +
                "<button onclick=\"deleteProduct(" + p.id + ")\" style=\"padding:5px 10px;font-size:10px;color:red;cursor:pointer\">Delete</button>" +
                "</td></tr>";
        }).join("");
    } catch (err) {
        showError(err);
    }
}

async function loadProductsForPOS() {
    try {
        await loadCategoriesForSelect();
        products = await apiCall("/products");
        renderPOSProducts(products);
    } catch (err) {
        showError(err);
    }
}

function renderPOSProducts(list) {
    const grid = document.getElementById("productGrid");
    if (!grid) return;

    if (!list || list.length === 0) {
        grid.innerHTML = "<p style=\"color:#999\">No products. Add some in the Products tab.</p>";
        return;
    }

    const display = list.slice(0, 60);
    grid.innerHTML = display.map(p => {
        // Expiry warning bar (matches v3.0 Standard)
        let expiryBar = "";
        if (p.expiry_date) {
            const today = new Date();
            const expiry = new Date(p.expiry_date);
            const daysLeft = Math.floor((expiry - today) / (1000 * 60 * 60 * 24));
            if (daysLeft < 0) {
                expiryBar = "<div style=\"background:#ffe5e5;color:#b71c1c;text-align:center;padding:3px 0;font-size:9px;font-weight:bold;border-radius:0 0 8px 8px;margin-top:5px\">EXPIRED</div>";
            } else if (daysLeft <= 7) {
                expiryBar = "<div style=\"background:#fff8e1;color:#e65100;text-align:center;padding:3px 0;font-size:9px;font-weight:bold;border-radius:0 0 8px 8px;margin-top:5px\">EXPIRES IN " + daysLeft + " DAYS</div>";
            }
        }
        return "<div class=\"product-card\" onclick=\"addToCart(" + p.id + ")\">" +
            "<div class=\"product-name\">" + p.name + "</div>" +
            (p.unit ? "<div style=\"font-size:10px;color:#666\">" + p.unit + "</div>" : "") +
            "<div class=\"product-price\">KSh " + p.price + "</div>" +
            (p.stock <= 0
                ? "<div style=\"background:#d32f2f;color:white;padding:2px 5px;border-radius:3px;font-size:9px\">OUT OF STOCK</div>"
                : "<div class=\"product-stock\">Stock: " + p.stock + "</div>") +
            expiryBar +
            "</div>";
    }).join("");
}

async function openProductModal() {
    await loadCategoriesForSelect();
    const f = document.getElementById("productForm");
    if (f) f.reset();
    openModal("productModal");
}

async function saveProduct() {
    const name = document.getElementById("productName").value.trim();
    const priceRaw = document.getElementById("productPrice").value;
    const stockRaw = document.getElementById("productStock").value;

    if (!name) { alert("Product name is required."); return; }
    if (!priceRaw) { alert("Price is required."); return; }
    if (stockRaw === "" || stockRaw === null) { alert("Stock is required."); return; }

    const catVal = document.getElementById("productCategory").value;
    const costVal = document.getElementById("productCost").value;

    const payload = {
        name: name,
        unit: document.getElementById("productUnit").value.trim() || null,
        category_id: catVal ? parseInt(catVal) : null,
        price: parseFloat(priceRaw),
        cost: costVal ? parseFloat(costVal) : null,
        tax_rate: parseFloat(document.getElementById("productTaxRate").value) || 0,
        stock: parseInt(stockRaw),
        low_stock_alert: parseInt(document.getElementById("productLowStockAlert").value) || 5,
        expiry_date: document.getElementById("productExpiry").value || null,
    };

    try {
        await apiCall("/products", "POST", payload);
        closeModal("productModal");
        showSuccess("Product added!");
        await loadProducts();
    } catch (err) {
        showError(err);
    }
}

async function openEditProductModal(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) { alert("Product not found."); return; }

    await loadCategoriesForSelect();

    document.getElementById("editProductId").value = product.id;
    document.getElementById("editProductName").value = product.name;
    document.getElementById("editProductUnit").value = product.unit || "";
    document.getElementById("editProductCategory").value = product.category_id || "";
    document.getElementById("editProductPrice").value = product.price;
    document.getElementById("editProductCost").value = product.cost || "";
    document.getElementById("editProductTaxRate").value = product.tax_rate || 0;
    document.getElementById("editProductStock").value = product.stock;
    document.getElementById("editProductLowStockAlert").value = product.low_stock_alert || 5;
    document.getElementById("editProductExpiry").value = product.expiry_date || "";

    openModal("editProductModal");
}

async function saveEditedProduct() {
    const productId = document.getElementById("editProductId").value;
    const name = document.getElementById("editProductName").value.trim();
    const priceRaw = document.getElementById("editProductPrice").value;
    const stockRaw = document.getElementById("editProductStock").value;

    if (!name) { alert("Product name is required."); return; }
    if (!priceRaw) { alert("Price is required."); return; }
    if (stockRaw === "") { alert("Stock is required."); return; }

    const catVal = document.getElementById("editProductCategory").value;
    const costVal = document.getElementById("editProductCost").value;

    const payload = {
        name: name,
        unit: document.getElementById("editProductUnit").value.trim() || null,
        category_id: catVal ? parseInt(catVal) : null,
        price: parseFloat(priceRaw),
        cost: costVal ? parseFloat(costVal) : null,
        tax_rate: parseFloat(document.getElementById("editProductTaxRate").value) || 0,
        stock: parseInt(stockRaw),
        low_stock_alert: parseInt(document.getElementById("editProductLowStockAlert").value) || 5,
        expiry_date: document.getElementById("editProductExpiry").value || null,
    };

    try {
        await apiCall("/products/" + productId, "PUT", payload);
        closeModal("editProductModal");
        showSuccess("Product updated!");
        await loadProducts();
    } catch (err) {
        showError(err);
    }
}

async function deleteProduct(id) {
    if (prompt("Type DELETE to confirm:") !== "DELETE") return;
    if (!confirm("Deactivate this product?")) return;
    try {
        await apiCall("/products/" + id, "DELETE");
        showSuccess("Product deactivated.");
        await loadProducts();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Stock adjustment
// ============================================================

function openStockModal(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;

    document.getElementById("stockProductId").value = product.id;
    document.getElementById("stockProductName").textContent = product.name;
    document.getElementById("stockCurrent").textContent = product.stock;
    document.getElementById("stockAdjustment").value = "";
    document.getElementById("stockReason").value = "";

    openModal("stockModal");
}

async function saveStockAdjustment() {
    const productId = document.getElementById("stockProductId").value;
    const adjustment = parseInt(document.getElementById("stockAdjustment").value);
    const reason = document.getElementById("stockReason").value || "manual";

    if (isNaN(adjustment) || adjustment === 0) {
        alert("Enter a non-zero adjustment (+/-).");
        return;
    }

    try {
        await apiCall("/products/" + productId + "/stock?adjustment=" + adjustment + "&reason=" + encodeURIComponent(reason), "PUT");
        closeModal("stockModal");
        showSuccess("Stock adjusted!");
        await loadProducts();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Event wiring for Part 2 (runs after page load)
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    // Category modal
    safeOn("categoryModal", "submit", function (e) { e.preventDefault(); });
    const catForm = document.getElementById("categoryForm");
    if (catForm) {
        catForm.addEventListener("submit", singleSubmit(saveCategory));
    }

    // Product modal
    const productForm = document.getElementById("productForm");
    if (productForm) {
        productForm.addEventListener("submit", singleSubmit(saveProduct));
    }

    // Edit product modal
    const editProductForm = document.getElementById("editProductForm");
    if (editProductForm) {
        editProductForm.addEventListener("submit", singleSubmit(saveEditedProduct));
    }

    // Stock modal
    const stockForm = document.getElementById("stockForm");
    if (stockForm) {
        stockForm.addEventListener("submit", singleSubmit(saveStockAdjustment));
    }

    // Search + filters
    safeOn("searchProduct", "input", function (e) {
        const q = e.target.value.toLowerCase();
        renderPOSProducts(products.filter(p => p.name.toLowerCase().includes(q)));
    });
    safeOn("posCategoryFilter", "change", function (e) {
        const catId = e.target.value;
        if (catId === "all") renderPOSProducts(products);
        else renderPOSProducts(products.filter(p => p.category_id == catId));
    });
    safeOn("barcodeInput", "keypress", function (e) {
        if (e.key !== "Enter") return;
        const code = e.target.value.trim();
        if (!code) return;
        const found = products.find(p => p.barcode === code);
        if (found) { addToCart(found.id); e.target.value = ""; }
    });
});


// ============================================================
//  Safari POS Pro - main.js
//  Part 3: Cart, Checkout, Payment, Receipt, Dashboard
// ============================================================

// ============================================================
//  Cart
// ============================================================

function addToCart(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) return;
    if (product.stock <= 0) { alert("OUT OF STOCK!"); return; }

    // Expiry check
    if (product.expiry_date && businessSettings) {
        const today = new Date();
        const expiry = new Date(product.expiry_date);
        const daysLeft = Math.floor((expiry - today) / (1000 * 60 * 60 * 24));
        if (daysLeft < 0 && businessSettings.block_expired === "true") {
            alert("CANNOT SELL! " + product.name + " EXPIRED " + Math.abs(daysLeft) + " days ago.");
            return;
        }
        if (daysLeft >= 0 && daysLeft <= 7 && businessSettings.warn_expiring === "true") {
            if (!confirm("WARNING: " + product.name + " expires in " + daysLeft + " days. Sell anyway?")) return;
        }
    }

    const existing = cart.find(i => i.product_id === productId);
    if (existing) {
        if (existing.quantity >= product.stock) { alert("NOT ENOUGH STOCK!"); return; }
        existing.quantity++;
    } else {
        cart.push({
            product_id: product.id,
            name: product.name,
            unit: product.unit,
            quantity: 1,
            unit_price: product.price,
            tax_rate: product.tax_rate || 0,
            stock: product.stock,
        });
    }
    updateCart();
}

function removeFromCart(productId) {
    cart = cart.filter(i => i.product_id !== productId);
    updateCart();
}

function updateQuantity(productId, change) {
    const item = cart.find(i => i.product_id === productId);
    if (!item) return;
    item.quantity += change;
    if (item.quantity <= 0) { removeFromCart(productId); return; }
    if (item.quantity > item.stock) {
        alert("NOT ENOUGH STOCK!");
        item.quantity -= change;
        return;
    }
    updateCart();
}

function updateCart() {
    const cartDiv = document.getElementById("cartItems");
    let subtotal = 0, taxAmount = 0;

    cart.forEach(item => {
        const lineTotal = item.quantity * item.unit_price;
        const taxRate = item.tax_rate || 0;
        const lineTax = taxRate > 0 ? lineTotal - (lineTotal / (1 + taxRate / 100)) : 0;
        subtotal += lineTotal;
        taxAmount += lineTax;
    });

    const discountAmount = subtotal * (discount / 100);
    const total = subtotal - discountAmount;

    if (cartDiv) {
        if (cart.length === 0) {
            cartDiv.innerHTML = "<p style=\"color:#95a5a6;text-align:center;margin-top:50px\">Cart is empty</p>";
        } else {
            cartDiv.innerHTML = cart.map(i => {
                const lineTotal = i.quantity * i.unit_price;
                const taxRate = i.tax_rate || 0;
                const lineTax = taxRate > 0 ? lineTotal - (lineTotal / (1 + taxRate / 100)) : 0;
                return "<div style=\"display:flex;align-items:center;justify-content:space-between;padding:2px;border-bottom:1px solid #f0f0f0;gap:2px;min-height:24px\">" +
                    "<div style=\"flex:2\"><strong style=\"font-size:11px\">" + i.name + "</strong>" +
                    (i.unit ? " <small>(" + i.unit + ")</small>" : "") +
                    "<br><small style=\"color:#666;font-size:9px\">KSh " + i.unit_price + " each</small></div>" +
                    "<div style=\"flex:1;display:flex;align-items:center;gap:8px;justify-content:center\">" +
                    "<button onclick=\"updateQuantity(" + i.product_id + ",-1)\" style=\"width:24px;height:24px;font-size:12px;background:#f0f0f0;color:#333;border:1px solid #ddd;border-radius:3px;cursor:pointer\">-</button>" +
                    "<span style=\"font-size:11px;font-weight:bold;min-width:20px;text-align:center\">" + i.quantity + "</span>" +
                    "<button onclick=\"updateQuantity(" + i.product_id + ",1)\" style=\"width:24px;height:24px;font-size:12px;background:#f0f0f0;color:#333;border:1px solid #ddd;border-radius:3px;cursor:pointer\">+</button></div>" +
                    "<div style=\"flex:1.5;text-align:right\"><strong style=\"font-size:11px\">KSh " + lineTotal.toFixed(2) + "</strong> " +
                    "<small style=\"color:#d2691e;font-size:9px\">Tax:" + lineTax.toFixed(2) + "</small></div>" +
                    "<button onclick=\"removeFromCart(" + i.product_id + ")\" style=\"background:#d32f2f;color:white;border:none;border-radius:5px;width:26px;height:26px;cursor:pointer;font-size:11px\">X</button></div>";
            }).join("");
        }
    }

    const st = document.getElementById("subtotal");
    if (st) st.textContent = "KSh " + subtotal.toFixed(2);
    const ct = document.getElementById("cartTax");
    if (ct) ct.textContent = "KSh " + taxAmount.toFixed(2);
    const dc = document.getElementById("discount");
    if (dc) dc.textContent = "-KSh " + discountAmount.toFixed(2);
    const tt = document.getElementById("total");
    if (tt) tt.textContent = "KSh " + total.toFixed(2);
}


// ============================================================
//  Checkout + Payment
// ============================================================

async function checkout() {
    if (cart.length === 0) { alert("Cart is empty!"); return; }

    for (const item of cart) {
        const product = products.find(p => p.id === item.product_id);
        if (product && product.stock <= 0) { alert("OUT OF STOCK: " + item.name); return; }
        if (product && item.quantity > product.stock) { alert("INSUFFICIENT STOCK: " + item.name); return; }
    }

    let total = 0;
    cart.forEach(i => { total += i.quantity * i.unit_price; });
    total -= (total * discount / 100);

    const pt = document.getElementById("paymentTotal");
    if (pt) pt.textContent = "KSh " + total.toFixed(2);
    const mps = document.getElementById("mpesaPhoneSection");
    if (mps) mps.style.display = "none";

    openModal("paymentModal");
}

async function processPayment(paymentMethod) {
    if (paymentMethod === "mpesa") {
        const sec = document.getElementById("mpesaPhoneSection");
        if (sec) sec.style.display = "block";
        return;
    }

    closeModal("paymentModal");

    const payload = {
        items: cart.map(i => ({
            product_id: i.product_id,
            quantity: i.quantity,
            unit_price: i.unit_price,
        })),
        payment_method: paymentMethod,
        discount: discount,
    };

    try {
        const sale = await apiCall("/sales/", "POST", payload);
        printReceipt(sale);
        cart = [];
        discount = 0;
        const di = document.getElementById("discountInput");
        if (di) di.value = 0;
        updateCart();
        await loadProductsForPOS();
        await loadDashboard();
    } catch (err) {
        showError(err);
    }
}

function normalizePhone(phone) {
    let cleaned = phone.replace(/\D/g, "");
    if (cleaned.startsWith("254")) return cleaned;
    if (cleaned.startsWith("0")) cleaned = cleaned.substring(1);
    return "254" + cleaned;
}

async function confirmMpesa() {
    const phoneRaw = document.getElementById("mpesaPhone").value.trim();
    const phone = normalizePhone(phoneRaw);

    if (!phone || phone.length !== 12) {
        alert("INVALID PHONE NUMBER!\n\nExamples:\n0741676521\n741676521\n0112168732");
        return;
    }

    let total = 0;
    cart.forEach(i => { total += i.quantity * i.unit_price; });
    total -= (total * discount / 100);

    closeModal("paymentModal");
    const sec = document.getElementById("mpesaPhoneSection");
    if (sec) sec.style.display = "none";
    const mp = document.getElementById("mpesaPhone");
    if (mp) mp.value = "";

    try {
        await apiCall("/mpesa/stk-push", "POST", {
            phone_number: phone,
            amount: total,
            receipt_no: "INV-" + Date.now(),
        });
        alert("M-Pesa prompt sent to " + phone + "!");
    } catch (err) {
        showError(err);
        return;
    }

    try {
        const sale = await apiCall("/sales/", "POST", {
            items: cart.map(i => ({
                product_id: i.product_id,
                quantity: i.quantity,
                unit_price: i.unit_price,
            })),
            payment_method: "mpesa",
            discount: discount,
        });
        printReceipt(sale);
        cart = [];
        discount = 0;
        const di = document.getElementById("discountInput");
        if (di) di.value = 0;
        updateCart();
        await loadProductsForPOS();
        await loadDashboard();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Receipt printing
// ============================================================

async function queueReceiptPrint(sale) {
    // Build HTML payload for the receipt (same content as printReceipt but as string)
    const html = buildReceiptHtml(sale, false);
    try {
        const result = await apiCall("/print-queue/enqueue", "POST", {
            job_type: "receipt",
            printer_name: "",  // use configured printer
            payload: html,
        });
        console.log("[auto-print] Queued job #" + result.job_id + " for printer: " + result.printer_name);
        return true;
    } catch (e) {
        console.warn("[auto-print] Failed to queue:", e.message);
        return false;
    }
}

function buildReceiptHtml(sale, isReprint) {
    let itemsHtml = "";
    sale.items.forEach(item => {
        const taxLabel = (item.tax_rate || 0) > 0 ? "A" : "B";
        itemsHtml += "<tr><td>" + item.name + (item.unit ? " (" + item.unit + ")" : "") + "</td>" +
            "<td style='text-align:center'>" + item.quantity + "</td>" +
            "<td style='text-align:center;font-weight:bold'>" + taxLabel + "</td>" +
            "<td style='text-align:right'>" + item.total_price.toFixed(2) + "</td></tr>";
    });

    const bs = businessSettings || {};
    const banner = isReprint
        ? "<div style='text-align:center;background:#fff3cd;border:2px solid #ffc107;padding:8px;margin:10px 0'><strong style='color:#d32f2f;font-size:13px'>*** REPRINTED COPY ***</strong></div>"
        : "";

    return "<!DOCTYPE html><html><head><title>Receipt</title><style>" +
        "body{font-family:'Courier New',monospace;padding:20px;max-width:300px;margin:auto}" +
        ".header{text-align:center;margin-bottom:15px}.header h2{margin:0;font-size:18px}.header p{margin:2px 0;font-size:10px}" +
        "hr{border:none;border-top:1px dashed #000;margin:10px 0}" +
        "table{width:100%;font-size:10px;border-collapse:collapse}td{padding:3px 0}" +
        ".total-row{font-weight:bold;font-size:11px}" +
        ".footer{text-align:center;margin-top:15px;font-size:9px}</style></head><body>" +
        "<div class='header'>" +
        "<h2>" + (bs.business_name || "Safari POS") + "</h2>" +
        "<p>" + [bs.business_po_box, bs.business_location].filter(Boolean).join(", ") + "</p>" +
        "<table style='width:100%;font-size:10px;margin-top:4px;border-collapse:collapse'><tr>" +
        "<td style='text-align:left;padding:0'>" + (bs.business_tax_pin ? "PIN: " + bs.business_tax_pin : "") + "</td>" +
        "<td style='text-align:right;padding:0'>" + (bs.business_phone ? "Tel: " + bs.business_phone : "") + "</td>" +
        "</tr></table>" +
        "</div><hr>" + banner +
        "<p style='font-size:10px'>Receipt: " + sale.receipt_no + "</p>" +
        "<p style='font-size:10px'>Date: " + new Date(sale.created_at).toLocaleString() + "</p><hr>" +
        "<table><thead><tr><th>Item</th><th style='text-align:center'>Qty</th><th style='text-align:center'>Tax</th><th style='text-align:right'>Amount</th></tr></thead><tbody>" +
        itemsHtml + "</tbody></table><hr>" +
        "<table>" +
        "<tr><td>Subtotal:</td><td style='text-align:right'>" + sale.subtotal.toFixed(2) + "</td></tr>" +
        "<tr><td>Tax (incl.):</td><td style='text-align:right'>" + sale.tax_amount.toFixed(2) + "</td></tr>" +
        "<tr class='total-row'><td>TOTAL:</td><td style='text-align:right'>KSh " + sale.total_amount.toFixed(2) + "</td></tr>" +
        "</table><hr>" +
        "<p style='font-size:10px'>Payment: " + sale.payment_method.toUpperCase() + "</p>" +
        "<p style='font-size:10px'>Served by: " + (authManager.getUser() ? authManager.getUser().name : "N/A") + "</p>" +
        "<div class='footer'><p>" + (bs.receipt_footer || "") + "</p><hr><p style='font-size:9px'>A = Taxable | B = Non-Taxable</p></div>" +
        "</body></html>";
}

function printReceipt(sale) {
    // If auto-print is on, queue silently instead of browser popup
    if (businessSettings && businessSettings.auto_print_receipt !== "false") {
        queueReceiptPrint(sale).then(queued => {
            if (queued) {
                console.log("[auto-print] Receipt queued for printing");
            } else {
                // Fall back to browser print if queue failed
                _browserPrintReceipt(sale);
            }
        });
        return;
    }
    _browserPrintReceipt(sale);
}

function _browserPrintReceipt(sale) {
    let itemsHtml = "";
    sale.items.forEach(item => {
        const taxLabel = (item.tax_rate || 0) > 0 ? "A" : "B";
        itemsHtml += "<tr><td>" + item.name + (item.unit ? " (" + item.unit + ")" : "") + "</td>" +
            "<td style='text-align:center'>" + item.quantity + "</td>" +
            "<td style='text-align:center;font-weight:bold'>" + taxLabel + "</td>" +
            "<td style='text-align:right'>" + item.total_price.toFixed(2) + "</td></tr>";
    });

    const bs = businessSettings || {};
    const html = "<!DOCTYPE html><html><head><title>Receipt</title><style>" +
        "body{font-family:'Courier New',monospace;padding:20px;max-width:300px;margin:auto}" +
        ".header{text-align:center;margin-bottom:15px}.header h2{margin:0;font-size:18px}.header p{margin:2px 0;font-size:10px}" +
        "hr{border:none;border-top:1px dashed #000;margin:10px 0}" +
        "table{width:100%;font-size:10px;border-collapse:collapse}td{padding:3px 0}" +
        ".total-row{font-weight:bold;font-size:11px}" +
        ".footer{text-align:center;margin-top:15px;font-size:9px}" +
        ".close-btn{display:block;margin:20px auto;padding:10px 20px;background:#8b4513;color:white;border:none;border-radius:5px;cursor:pointer}" +
        "@media print{.close-btn{display:none}}</style></head><body>" +
        "<div class='header'><h2>" + (bs.business_name || "Safari POS") + "</h2>" +
        (bs.business_po_box ? "<p>" + bs.business_po_box + "</p>" : "") +
        (bs.business_location ? "<p>" + bs.business_location + "</p>" : "") +
        (bs.business_tax_pin ? "<p>PIN: " + bs.business_tax_pin + "</p>" : "") +
        (bs.business_phone ? "<p>Tel: " + bs.business_phone + "</p>" : "") +
        "</div><hr>" +
        "<p style='font-size:10px'>Receipt: " + sale.receipt_no + "</p>" +
        "<p style='font-size:10px'>Date: " + new Date(sale.created_at).toLocaleString() + "</p><hr>" +
        "<table><thead><tr><th>Item</th><th style='text-align:center'>Qty</th><th style='text-align:center'>Tax</th><th style='text-align:right'>Amount</th></tr></thead><tbody>" +
        itemsHtml + "</tbody></table><hr>" +
        "<table>" +
        "<tr><td>Subtotal:</td><td style='text-align:right'>" + sale.subtotal.toFixed(2) + "</td></tr>" +
        "<tr><td>Tax (incl.):</td><td style='text-align:right'>" + sale.tax_amount.toFixed(2) + "</td></tr>" +
        "<tr class='total-row'><td>TOTAL:</td><td style='text-align:right'>KSh " + sale.total_amount.toFixed(2) + "</td></tr>" +
        "</table><hr>" +
        "<p style='font-size:10px'>Payment: " + sale.payment_method.toUpperCase() + "</p>" +
        "<p style='font-size:10px'>Served by: " + (authManager.getUser() ? authManager.getUser().name : "N/A") + "</p>" +
        "<div class='footer'><p>" + (bs.receipt_footer || "") + "</p><hr><p style='font-size:9px'>A = Taxable | B = Non-Taxable</p></div>" +
        "<button class='close-btn' onclick='window.close()'>Close</button></body></html>";

    const pw = window.open("", "Receipt", "width=400,height=600");
    if (!pw) { alert("Please allow popups to print receipts."); return; }
    pw.document.write(html);
    pw.document.close();
    setTimeout(() => { try { pw.print(); } catch (e) {} }, 1000);
    setTimeout(() => { try { pw.close(); } catch (e) {} }, 15000);
}


// ============================================================
//  Dashboard
// ============================================================

async function loadDashboard() {
    try {
        const data = await apiCall("/sales/today");
        const ts = document.getElementById("todaySales");
        if (ts) ts.textContent = data.count;
        const tr = document.getElementById("todayRevenue");
        if (tr) tr.textContent = "KSh " + data.total_amount.toFixed(2);

        const tbody = document.getElementById("todaySalesTableBody");
        if (tbody && data.sales) {
            if (data.sales.length === 0) {
                tbody.innerHTML = "<tr><td colspan=\"5\">No sales yet today</td></tr>";
            } else {
                tbody.innerHTML = data.sales.map(s =>
                    "<tr><td>" + s.receipt_no + "</td><td>" + s.created_at + "</td><td>" +
                    s.cashier + "</td><td>" + s.payment_method.toUpperCase() +
                    "</td><td>KSh " + s.total_amount.toFixed(2) + "</td></tr>"
                ).join("");
            }
        }
    } catch (err) {
        console.error("[loadDashboard]", err);
    }
    // Also refresh low-stock alerts so the dashboard shows them on load
    try {
        if (typeof loadLowStock === "function") {
            await loadLowStock();
        }
    } catch (err) {
        console.error("[loadDashboard->loadLowStock]", err);
    }
}


// ============================================================
//  Receipt history + reprint
// ============================================================

async function loadReceiptHistory() {
    try {
        const receipts = await apiCall("/sales/history");
        const user = authManager.getUser();
        const isAdminManager = user && (user.role === "admin" || user.role === "manager");
        const tbody = document.getElementById("receiptHistoryBody");
        if (!tbody) return;

        if (!receipts || receipts.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"6\">No receipts yet</td></tr>";
            return;
        }

        tbody.innerHTML = receipts.map((r, index) => {
            let btn = "";
            if (isAdminManager) {
                btn = "<button onclick=\"reprintReceipt('" + r.receipt_no + "')\" style=\"padding:5px 10px;font-size:10px;cursor:pointer\">Reprint</button>";
            } else {
                btn = index === 0
                    ? "<button onclick=\"reprintLastReceiptOnly()\" style=\"padding:5px 10px;font-size:10px;cursor:pointer\">Reprint</button>"
                    : "<span style=\"color:#999;font-size:9px\">View only</span>";
            }
            const delBtn = isAdminManager
                ? "<button onclick=\"deleteReceipt('" + r.receipt_no + "')\" style=\"color:red;padding:3px 8px;font-size:11px;margin-left:5px;cursor:pointer\">Delete</button>"
                : "";
            return "<tr><td>" + r.receipt_no + "</td><td>" + r.created_at + "</td><td>" +
                r.cashier + "</td><td>" + r.items.length + "</td><td>KSh " +
                r.total_amount.toFixed(2) + "</td><td>" + btn + delBtn + "</td></tr>";
        }).join("");
    } catch (err) {
        showError(err);
    }
}

async function reprintLastReceiptOnly() {
    try {
        const receipt = await apiCall("/sales/last-receipt");
        if (!receipt || receipt.message) { alert("No receipt available."); return; }
        let settings = businessSettings;
        if (!settings) { try { settings = await apiCall("/settings/"); } catch (e) { settings = {}; } }
        _printReceiptObject(receipt, settings, false);
    } catch (err) {
        showError(err);
    }
}

async function reprintReceipt(receiptNo) {
    try {
        const receipts = await apiCall("/sales/history");
        const receipt = receipts.find(r => r.receipt_no === receiptNo);
        if (!receipt) { alert("Receipt not found"); return; }
        let settings = businessSettings;
        if (!settings) { try { settings = await apiCall("/settings/"); } catch (e) { settings = {}; } }
        _printReceiptObject(receipt, settings, true);
    } catch (err) {
        showError(err);
    }
}

function _printReceiptObject(receipt, settings, showReprintBanner) {
    let itemsHtml = "";
    receipt.items.forEach(item => {
        const taxLabel = (item.tax_rate || 0) > 0 ? "A" : "B";
        itemsHtml += "<tr><td>" + item.name + "</td><td style='text-align:center'>" + item.quantity +
            "</td><td style='text-align:center;font-weight:bold'>" + taxLabel +
            "</td><td style='text-align:right'>" + item.total_price.toFixed(2) + "</td></tr>";
    });

    const banner = showReprintBanner
        ? "<div style='text-align:center;background:#fff3cd;border:2px solid #ffc107;padding:8px;margin:10px 0'><strong style='color:#d32f2f;font-size:13px'>*** REPRINTED COPY ***</strong></div>"
        : "";

    const html = "<!DOCTYPE html><html><head><title>Reprint</title><style>" +
        "body{font-family:'Courier New',monospace;padding:20px;max-width:300px;margin:auto}" +
        ".h{text-align:center;margin-bottom:10px}.h h2{margin:0;font-size:16px}.h p{margin:2px 0;font-size:10px}" +
        "hr{border:none;border-top:1px dashed #000;margin:10px 0}" +
        "table{width:100%;font-size:11px;border-collapse:collapse}td{padding:3px 0}" +
        ".tr{font-weight:bold;font-size:12px}" +
        ".cb{display:block;margin:20px auto;padding:10px 20px;background:#8b4513;color:white;border:none;border-radius:5px;cursor:pointer}" +
        "@media print{.cb{display:none}}</style></head><body>" +
        "<div class='h'><h2>" + (settings.business_name || "Safari POS") + "</h2>" +
        "<p>" + [settings.business_po_box, settings.business_location].filter(Boolean).join(", ") + "</p>" +
        "<table style='width:100%;font-size:10px;margin-top:4px;border-collapse:collapse'><tr>" +
        "<td style='text-align:left;padding:0'>" + (settings.business_tax_pin ? "PIN: " + settings.business_tax_pin : "") + "</td>" +
        "<td style='text-align:right;padding:0'>" + (settings.business_phone ? "Tel: " + settings.business_phone : "") + "</td>" +
        "</tr></table>" +
        "</div><hr>" + banner + "<hr>" +
        "<p style='font-size:11px'>Receipt: " + receipt.receipt_no + "</p>" +
        "<p style='font-size:11px'>Date: " + receipt.created_at + "</p><hr>" +
        "<table><thead><tr><th>Item</th><th style='text-align:center'>Qty</th><th style='text-align:center'>Tax</th><th style='text-align:right'>Amount</th></tr></thead><tbody>" +
        itemsHtml + "</tbody></table><hr>" +
        "<table>" +
        "<tr><td>Subtotal:</td><td style='text-align:right'>" + receipt.subtotal.toFixed(2) + "</td></tr>" +
        "<tr><td>Tax (incl.):</td><td style='text-align:right'>" + receipt.tax_amount.toFixed(2) + "</td></tr>" +
        "<tr class='tr'><td>TOTAL:</td><td style='text-align:right'>KSh " + receipt.total_amount.toFixed(2) + "</td></tr>" +
        "</table><hr>" +
        "<p style='font-size:11px'>Payment: " + receipt.payment_method.toUpperCase() + "</p>" +
        "<p style='font-size:11px'>Served by: " + (receipt.cashier || "N/A") + "</p>" +
        "<p style='font-size:9px'>A = Taxable | B = Non-Taxable</p>" +
        "<button class='cb' onclick='window.close()'>Close</button></body></html>";

    const pw = window.open("", "Reprint", "width=400,height=600");
    if (!pw) { alert("Please allow popups to print receipts."); return; }
    pw.document.write(html);
    pw.document.close();
    setTimeout(() => { try { pw.print(); } catch (e) {} }, 1000);
    setTimeout(() => { try { pw.close(); } catch (e) {} }, 15000);
}

async function deleteReceipt(receiptNo) {
    if (prompt("Type DELETE to confirm removal of " + receiptNo + ":") !== "DELETE") return;
    if (!confirm("Delete this receipt? Tax records will be kept.")) return;
    try {
        await apiCall("/sales/receipt/" + receiptNo, "DELETE");
        showSuccess("Receipt deleted.");
        await loadReceiptHistory();
        await loadDashboard();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Event wiring for Part 3
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    // Discount input
    safeOn("discountInput", "input", function (e) {
        discount = parseFloat(e.target.value) || 0;
        updateCart();
    });

    // Ensure cart displays initially
    updateCart();
});


// ============================================================
//  Safari POS Pro - main.js
//  Part 4: Users, Settings, Purchase Orders, Reports, Backup
// ============================================================

// ============================================================
//  Users
// ============================================================

async function loadUsers() {
    try {
        const users = await apiCall("/users/");
        const currentUser = authManager.getUser();
        const tbody = document.getElementById("usersTableBody");
        if (!tbody) return;

        if (!users || users.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"6\">No users</td></tr>";
            return;
        }

        tbody.innerHTML = users.map(u => {
            const isSelf = currentUser && u.id === currentUser.id;
            const isAdmin = currentUser && currentUser.role === "admin";
            const isManager = currentUser && currentUser.role === "manager";
            let actions = "";

            const canEdit = isAdmin || (isManager && u.role === "cashier");
            if (canEdit) {
                actions += "<button onclick=\"openEditUserModal(" + u.id + ")\" style=\"padding:5px 10px;font-size:10px;margin-right:3px;background:#2e7d32;color:white;border:none;border-radius:3px;cursor:pointer\">Edit</button>";
            }

            const canDelete = isAdmin && !isSelf && (u.role !== "admin" || users.filter(x => x.role === "admin").length > 1);
            if (canDelete) {
                actions += "<button onclick=\"deleteUser(" + u.id + ")\" style=\"padding:5px 10px;font-size:10px;color:red;cursor:pointer\">Remove</button>";
            } else if (isSelf) {
                actions += "<span style=\"color:#999;font-size:9px\">You</span>";
            }

            return "<tr><td>" + u.id + "</td><td>" + u.name + "</td><td>" +
                (u.email || "-") + "</td><td>" + (u.phone || "-") + "</td><td>" +
                u.role.toUpperCase() + "</td><td>" + actions + "</td></tr>";
        }).join("");
    } catch (err) {
        showError(err);
    }
}

function openUserModal() {
    const form = document.getElementById("userForm");
    if (form) form.reset();
    openModal("userModal");
}

async function saveUser() {
    const name = document.getElementById("userNameInput").value.trim();
    const email = document.getElementById("userEmail").value.trim();
    const phone = document.getElementById("userPhone").value.trim();
    const password = document.getElementById("userPassword").value;
    const role = document.getElementById("userRoleSelect").value;

    if (!name) { alert("Name is required."); return; }
    if (!email && !phone) {
        alert("Please enter at least an EMAIL or a PHONE number.");
        return;
    }
    if (!password) { alert("Password is required."); return; }
    if (!role) { alert("Please select a role."); return; }

    const payload = {
        name: name,
        email: email || null,
        phone: phone || null,
        password: password,
        role: role,
    };

    try {
        await apiCall("/users/", "POST", payload);
        closeModal("userModal");
        showSuccess("User added!");
        await loadUsers();
    } catch (err) {
        showError(err);
    }
}

async function openEditUserModal(userId) {
    try {
        const users = await apiCall("/users/");
        const user = users.find(u => u.id === userId);
        if (!user) { alert("User not found."); return; }

        document.getElementById("editUserId").value = user.id;
        document.getElementById("editUserName").value = user.name || "";
        document.getElementById("editUserEmail").value = user.email || "";
        document.getElementById("editUserPhone").value = user.phone || "";
        document.getElementById("editUserPassword").value = "";
        document.getElementById("editUserRole").value = user.role || "cashier";

        const currentUser = authManager.getUser();
        const roleGroup = document.getElementById("editUserRoleGroup");
        if (roleGroup) roleGroup.style.display = (currentUser.role === "admin") ? "block" : "none";

        openModal("editUserModal");
    } catch (err) {
        showError(err);
    }
}

async function saveEditedUser() {
    const userId = document.getElementById("editUserId").value;
    const name = document.getElementById("editUserName").value.trim();
    const email = document.getElementById("editUserEmail").value.trim();
    const phone = document.getElementById("editUserPhone").value.trim();
    const pwd = document.getElementById("editUserPassword").value;

    if (!name) { alert("Name is required."); return; }
    if (!email && !phone) {
        alert("At least one of email or phone is required.");
        return;
    }

    const payload = {
        name: name,
        email: email || null,
        phone: phone || null,
    };
    if (pwd) payload.password = pwd;

    const currentUser = authManager.getUser();
    if (currentUser.role === "admin") {
        payload.role = document.getElementById("editUserRole").value;
    }

    try {
        await apiCall("/users/" + userId + "/admin-edit", "PUT", payload);
        closeModal("editUserModal");
        showSuccess("User updated!");
        await loadUsers();
    } catch (err) {
        showError(err);
    }
}

async function deleteUser(id) {
    if (prompt("Type DELETE to confirm:") !== "DELETE") return;
    if (!confirm("Permanently remove this user? Sales history will be preserved.")) return;
    try {
        await apiCall("/users/" + id, "DELETE");
        showSuccess("User removed.");
        await loadUsers();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Reports
// ============================================================

async function loadDailyClose() {
    try {
        const data = await apiCall("/sales/daily-close");
        const d = document.getElementById("dailyCloseDate");
        if (d) d.textContent = data.date;
        const t = document.getElementById("dailyCloseTransactions");
        if (t) t.textContent = data.total_transactions;
        const tbody = document.getElementById("dailyCloseTableBody");
        if (tbody) {
            tbody.innerHTML =
                "<tr><td>Cash</td><td style='text-align:right'>KSh " + data.cash_total.toFixed(2) + "</td></tr>" +
                "<tr><td>M-Pesa</td><td style='text-align:right'>KSh " + data.mpesa_total.toFixed(2) + "</td></tr>" +
                "<tr><td>Card</td><td style='text-align:right'>KSh " + data.card_total.toFixed(2) + "</td></tr>" +
                "<tr style='font-weight:bold'><td>TOTAL</td><td style='text-align:right'>KSh " + data.grand_total.toFixed(2) + "</td></tr>";
        }
    } catch (err) {
        console.error("[loadDailyClose]", err);
    }
}

async function loadProfitReport() {
    try {
        const data = await apiCall("/reports/profit");
        const tbody = document.getElementById("profitTableBody");
        if (!tbody) return;
        if (!data || data.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"7\">No cost data yet</td></tr>";
            return;
        }
        tbody.innerHTML = data.map(p =>
            "<tr><td>" + p.product + "</td><td>KSh " + p.selling_price +
            "</td><td>" + p.tax_rate + "%</td><td>KSh " + p.net_selling +
            "</td><td>KSh " + (p.cost || 0) + "</td><td>KSh " + p.gross_profit +
            "</td><td>" + p.profit_margin + "%</td></tr>"
        ).join("");
    } catch (err) {
        console.error("[loadProfitReport]", err);
    }
}

async function loadAllSales() {
    try {
        const sales = await apiCall("/sales/all");
        const tbody = document.getElementById("allSalesTableBody");
        if (!tbody) return;
        if (!sales || sales.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"5\">No sales yet</td></tr>";
            return;
        }
        tbody.innerHTML = sales.map(s =>
            "<tr><td>" + s.receipt_no + "</td><td>" + s.created_at + "</td><td>" +
            s.cashier + "</td><td>KSh " + s.total_amount.toFixed(2) +
            "</td><td><button onclick=\"deleteReceipt('" + s.receipt_no + "')\" style=\"color:red;padding:3px 8px;font-size:11px;cursor:pointer\">Delete</button></td></tr>"
        ).join("");
    } catch (err) {
        console.error("[loadAllSales]", err);
    }
}

async function loadLowStock() {
    try {
        const items = await apiCall("/reports/low-stock");
        const html = (items && items.length > 0)
            ? items.map(p =>
                "<div style='padding:10px;background:#fff3cd;margin-bottom:5px;border-radius:5px;border-left:4px solid #ffc107'>" +
                "<strong>" + p.name + "</strong> — Stock: <strong style='color:#d32f2f'>" +
                p.stock + "</strong> <small style='color:#666'>(alert threshold: ≤ " +
                (p.low_stock_alert || 5) + ")</small></div>"
            ).join("")
            : "<p style='color:#2e7d32'>No low stock items (all products have stock above their threshold)</p>";
        const l1 = document.getElementById("lowStockList");
        if (l1) l1.innerHTML = html;
        const l2 = document.getElementById("lowStockListReports");
        if (l2) l2.innerHTML = html;
    } catch (err) {
        console.error("[loadLowStock]", err);
    }
}

function printSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;
    const pw = window.open("", "Print", "width=800,height=600");
    if (!pw) { alert("Please allow popups to print."); return; }
    pw.document.write("<html><head><title>Print</title><style>body{font-family:Arial;padding:20px}table{width:100%;border-collapse:collapse}th,td{padding:8px;border:1px solid #ddd;text-align:left}th{background:#8b4513;color:white}h2{color:#8b4513}</style></head><body>");
    pw.document.write(section.innerHTML);
    pw.document.write("</body></html>");
    pw.document.close();
    setTimeout(() => { pw.print(); }, 500);
}


// ============================================================
//  Purchase Orders
// ============================================================

async function openPOModal() {
    await loadProductsForPO();
    const f = document.getElementById("poForm");
    if (f) f.reset();
    openModal("poModal");
}

async function loadProductsForPO() {
    try {
        const list = await apiCall("/products");
        const select = document.getElementById("poProductId");
        if (select) {
            if (!list || list.length === 0) {
                select.innerHTML = "<option value=\"\">No products available</option>";
            } else {
                select.innerHTML = "<option value=\"\">Select Product...</option>" +
                    list.map(p => "<option value=\"" + p.id + "\">" + p.name + " (" + (p.unit || "N/A") + ")</option>").join("");
            }
        }
    } catch (err) {
        console.error("[loadProductsForPO]", err);
    }
}

async function loadPurchaseOrders() {
    try {
        const grouped = await apiCall("/purchase-orders/by-date");
        const tbody = document.getElementById("poTableBody");
        if (!tbody) return;

        const dates = Object.keys(grouped || {}).sort().reverse();
        if (dates.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"10\">No purchase orders yet</td></tr>";
            return;
        }

        let html = "";
        dates.forEach(date => {
            const pos = grouped[date];
            const dayTotal = pos.reduce((sum, p) => sum + p.total_cost, 0);
            html += "<tr style=\"background:#f5e6d3;font-weight:bold\"><td colspan=\"7\">" +
                date + " — " + pos.length + " POs — Total: KSh " + dayTotal.toFixed(2) +
                "</td><td colspan=\"3\" style=\"text-align:right\">" +
                "<button onclick=\"printPODay('" + date + "')\" style=\"background:#0088cc;color:white;padding:4px 10px;border:none;border-radius:3px;cursor:pointer;font-size:11px;margin-right:5px\">Print Day</button>" +
                "<button onclick=\"deletePODay('" + date + "')\" style=\"background:#d32f2f;color:white;padding:4px 10px;border:none;border-radius:3px;cursor:pointer;font-size:11px\">Delete Day</button>" +
                "</td></tr>";
            pos.forEach(po => {
                html += "<tr><td>" + po.id + "</td><td>" + po.supplier + "</td><td>" +
                    po.product_name + "</td><td>" + (po.unit || "-") + "</td><td>" +
                    po.quantity + "</td><td>KSh " + po.unit_cost + "</td><td>KSh " +
                    po.total_cost + "</td><td>" + po.status.toUpperCase() + "</td><td>" +
                    (po.status === "pending"
                        ? "<button onclick=\"updatePOStatus(" + po.id + ",'received')\" style=\"padding:3px 8px;font-size:11px;cursor:pointer\">Receive</button>"
                        : "-") +
                    "</td><td><button onclick=\"deletePO(" + po.id + ")\" style=\"color:red;padding:3px 8px;font-size:11px;cursor:pointer\">Delete</button></td></tr>";
            });
        });
        tbody.innerHTML = html;
    } catch (err) {
        showError(err);
    }
}

async function savePO() {
    const supplier = document.getElementById("poSupplier").value.trim();
    const productId = document.getElementById("poProductId").value;
    const qty = document.getElementById("poQuantity").value;
    const cost = document.getElementById("poUnitCost").value;

    if (!supplier) { alert("Supplier is required."); return; }
    if (!productId) { alert("Please select a product."); return; }
    if (!qty || parseInt(qty) < 1) { alert("Quantity must be at least 1."); return; }
    if (!cost) { alert("Unit cost is required."); return; }

    try {
        await apiCall("/purchase-orders/", "POST", {
            supplier: supplier,
            product_id: parseInt(productId),
            quantity: parseInt(qty),
            unit_cost: parseFloat(cost),
        });
        closeModal("poModal");
        showSuccess("PO created!");
        await loadPurchaseOrders();
    } catch (err) {
        showError(err);
    }
}

async function updatePOStatus(poId, status) {
    try {
        await apiCall("/purchase-orders/" + poId + "/status?status=" + status, "PUT");
        showSuccess("PO marked as received. Stock updated.");
        await loadPurchaseOrders();
        await loadProducts();
    } catch (err) {
        showError(err);
    }
}

async function deletePO(id) {
    if (prompt("Type DELETE to confirm:") !== "DELETE") return;
    try {
        await apiCall("/purchase-orders/" + id, "DELETE");
        showSuccess("PO deleted.");
        await loadPurchaseOrders();
    } catch (err) {
        showError(err);
    }
}

async function deletePODay(date) {
    if (prompt("Type DELETE to remove ALL POs for " + date + ":") !== "DELETE") return;
    if (!confirm("Delete all POs for " + date + "?")) return;
    try {
        const result = await apiCall("/purchase-orders/delete-day/" + date, "DELETE");
        showSuccess(result.message);
        await loadPurchaseOrders();
    } catch (err) {
        showError(err);
    }
}

async function printPODay(date) {
    try {
        const pos = await apiCall("/purchase-orders/by-date/" + date);
        if (!pos || pos.length === 0) { alert("No POs for this date"); return; }
        let itemsHtml = "";
        let total = 0;
        pos.forEach(p => {
            itemsHtml += "<tr><td>" + p.id + "</td><td>" + p.supplier + "</td><td>" +
                p.product_name + " " + (p.unit || "") + "</td><td>" + p.quantity +
                "</td><td>KSh " + p.unit_cost + "</td><td>KSh " + p.total_cost + "</td></tr>";
            total += p.total_cost;
        });
        const html = "<!DOCTYPE html><html><head><title>PO Report " + date + "</title><style>body{font-family:Arial;padding:20px}h2{text-align:center}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background:#8b4513;color:white}.total{font-weight:bold;background:#f5e6d3}</style></head><body><h2>Purchase Orders Report</h2><p style='text-align:center'>Date: " + date + "</p><table><thead><tr><th>ID</th><th>Supplier</th><th>Product</th><th>Qty</th><th>Unit Cost</th><th>Total</th></tr></thead><tbody>" + itemsHtml + "<tr class='total'><td colspan='5'>TOTAL</td><td>KSh " + total.toFixed(2) + "</td></tr></tbody></table></body></html>";
        const pw = window.open("", "POReport", "width=800,height=600");
        if (!pw) { alert("Please allow popups."); return; }
        pw.document.write(html);
        pw.document.close();
        setTimeout(() => { try { pw.print(); } catch (e) {} }, 500);
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Settings
// ============================================================

async function loadSettings() {
    try {
        const settings = await apiCall("/settings/");
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ""; };
        set("defaultTaxRate", settings.default_tax_rate);
        set("businessName", settings.business_name);
        set("businessPoBox", settings.business_po_box);
        set("businessLocation", settings.business_location);
        set("businessPhone", settings.business_phone);
        set("businessTaxPin", settings.business_tax_pin);
        set("receiptFooter", settings.receipt_footer);
    } catch (err) {
        console.error("[loadSettings]", err);
    }
}

async function updateBusinessInfo() {
    const payload = {
        business_name: document.getElementById("businessName").value,
        business_po_box: document.getElementById("businessPoBox").value,
        business_location: document.getElementById("businessLocation").value,
        business_phone: document.getElementById("businessPhone").value,
        business_tax_pin: document.getElementById("businessTaxPin").value,
        receipt_footer: document.getElementById("receiptFooter").value,
    };
    try {
        await apiCall("/settings/business", "PUT", payload);
        showSuccess("Business information saved!");
        businessSettings = await apiCall("/settings/");
    } catch (err) {
        showError(err);
    }
}

async function updateTaxRate() {
    const rate = document.getElementById("defaultTaxRate").value;
    try {
        await apiCall("/settings/tax-rate?rate=" + rate, "PUT");
        showSuccess("Tax rate updated!");
        await loadProducts();
    } catch (err) {
        showError(err);
    }
}

async function loadBusinessSettings() {
    try {
        businessSettings = await apiCall("/settings/");
    } catch (err) {
        businessSettings = {};
    }
}

async function loadMpesaSettings() {
    try {
        const s = await apiCall("/settings/");
        const setCheck = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };
        const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ""; };
        setCheck("mpesaEnabled", s.mpesa_enabled === "true");
        setVal("mpesaConsumerKey", s.mpesa_consumer_key);
        setVal("mpesaConsumerSecret", s.mpesa_consumer_secret);
        setVal("mpesaPasskey", s.mpesa_passkey);
        setVal("mpesaShortcode", s.mpesa_shortcode);
    } catch (err) {
        console.error("[loadMpesaSettings]", err);
    }
}

async function saveMpesaSettings() {
    const payload = {
        mpesa_enabled: document.getElementById("mpesaEnabled").checked ? "true" : "false",
        mpesa_consumer_key: document.getElementById("mpesaConsumerKey").value,
        mpesa_consumer_secret: document.getElementById("mpesaConsumerSecret").value,
        mpesa_passkey: document.getElementById("mpesaPasskey").value,
        mpesa_shortcode: document.getElementById("mpesaShortcode").value,
    };
    try {
        await apiCall("/settings/business", "PUT", payload);
        showSuccess("M-Pesa settings saved!");
    } catch (err) {
        showError(err);
    }
}

async function loadExpirySettings() {
    try {
        const s = await apiCall("/settings/");
        const setCheck = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };
        setCheck("blockExpired", s.block_expired === "true");
        setCheck("warnExpiring", s.warn_expiring === "true");
    } catch (err) {
        console.error("[loadExpirySettings]", err);
    }
}

async function saveExpirySettings() {
    const payload = {
        block_expired: document.getElementById("blockExpired").checked ? "true" : "false",
        warn_expiring: document.getElementById("warnExpiring").checked ? "true" : "false",
    };
    try {
        await apiCall("/settings/business", "PUT", payload);
        showSuccess("Expiry settings saved!");
    } catch (err) {
        showError(err);
    }
}

async function generateRecoveryCode() {
    if (!confirm("This will REPLACE any existing recovery code. Continue?")) return;
    try {
        const result = await apiCall("/settings/generate-recovery-code", "POST");
        prompt("RECOVERY CODE - COPY THIS NOW!\n\n(Ctrl+C to copy)", result.code);
    } catch (err) {
        showError(err);
    }
}

async function resetDemoData() {
    if (confirm("Create a BACKUP before reset? (recommended)")) {
        try {
            const result = await apiCall("/backup/create?location=desktop", "POST");
            alert("Backup created: " + result.filename);
        } catch (err) {
            if (!confirm("Backup failed: " + err.message + "\n\nContinue with reset anyway?")) return;
        }
    }
    if (prompt("Type RESET to clear ALL demo data:") !== "RESET") {
        alert("Reset cancelled.");
        return;
    }
    if (!confirm("FINAL WARNING: This will DELETE all products, sales, categories, tax records, and non-admin users. Admin account and settings will be kept. Continue?")) return;
    try {
        const result = await apiCall("/settings/reset-demo", "POST");
        alert("Demo data cleared.\n\nBackup saved to:\n" + result.backup_created + "\n\nRestart the server.");
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Backup
// ============================================================

function createBackup() {
    openModal("backupLocationModal");
}

async function backupToDesktop() {
    closeModal("backupLocationModal");
    try {
        const result = await apiCall("/backup/create?location=desktop", "POST");
        showSuccess("Backup created at:\n" + result.saved_to);
    } catch (err) {
        showError(err);
    }
}

async function backupToFlash() {
    closeModal("backupLocationModal");
    try {
        const data = await apiCall("/backup/drives");
        if (!data.drives || data.drives.length === 0) {
            alert("No drives detected!");
            return;
        }
        let list = "Available drives:\n";
        data.drives.forEach((d, i) => { list += (i + 1) + ". " + d + "\n"; });
        list += "\nEnter number to select:";
        const choice = prompt(list, "1");
        if (!choice) return;
        const idx = parseInt(choice) - 1;
        if (idx < 0 || idx >= data.drives.length) { alert("Invalid selection"); return; }
        const result = await apiCall("/backup/create?location=" + encodeURIComponent(data.drives[idx]), "POST");
        showSuccess("Backup created at:\n" + result.saved_to);
    } catch (err) {
        showError(err);
    }
}

async function restoreSelectedFile() {
    const fi = document.getElementById("restoreFileInput");
    if (!fi || !fi.files || fi.files.length === 0) {
        alert("Please select a backup file first.");
        return;
    }
    const file = fi.files[0];
    if (prompt("Type RESTORE to confirm:") !== "RESTORE") return;
    if (!confirm("All current data will be replaced with " + file.name + "!")) return;
    try {
        const formData = new FormData();
        formData.append("file", file);
        const response = await fetch(API_BASE_URL + "/backup/restore-file", {
            method: "POST",
            headers: { "Authorization": "Bearer " + authManager.token },
            body: formData,
        });
        if (!response.ok) {
            const e = await response.json().catch(() => ({}));
            throw new Error(e.detail || "Restore failed");
        }
        const result = await response.json();
        showSuccess(result.message);
    } catch (err) {
        showError(err);
    }
}

async function restoreDataOnly() {
    const fi = document.getElementById("restoreFileInput");
    if (!fi || !fi.files || fi.files.length === 0) { alert("Select a backup file first."); return; }
    const filename = fi.files[0].name;
    if (prompt("Type DATA-RESTORE to confirm:") !== "DATA-RESTORE") return;
    if (!confirm("This replaces all products, sales, categories. Users will be preserved.")) return;
    try {
        const result = await apiCall("/backup/restore-data-only/" + filename, "POST");
        showSuccess(result.message + "\nRestored: " + (result.restored_tables || []).join(", "));
    } catch (err) {
        showError(err);
    }
}

function openSelectiveRestoreModal() {
    const fi = document.getElementById("restoreFileInput");
    if (!fi || !fi.files || fi.files.length === 0) {
        alert("Select a backup file first.");
        return;
    }
    openModal("selectiveRestoreModal");
}

async function restoreSelective() {
    const fi = document.getElementById("restoreFileInput");
    const filename = fi.files[0].name;
    const tables = [];
    if (document.getElementById("sel_products").checked) tables.push("products");
    if (document.getElementById("sel_categories").checked) tables.push("categories");
    if (document.getElementById("sel_tax_ledger").checked) tables.push("tax_ledger");
    if (document.getElementById("sel_sales").checked) { tables.push("sales"); tables.push("sale_items"); }
    if (document.getElementById("sel_purchase_orders").checked) tables.push("purchase_orders");
    if (tables.length === 0) { alert("Select at least one table."); return; }
    if (prompt("Type SELECTIVE-RESTORE to confirm:\n\nTables: " + tables.join(", ")) !== "SELECTIVE-RESTORE") return;
    try {
        const result = await apiCall("/backup/restore-selective/" + filename + "?tables=" + encodeURIComponent(tables.join(",")), "POST");
        showSuccess(result.message + "\nRestored: " + (result.restored_tables || []).join(", "));
        closeModal("selectiveRestoreModal");
    } catch (err) {
        showError(err);
    }
}

async function deleteSalesBefore() {
    const date = prompt("Delete all sales before (YYYY-MM-DD):");
    if (!date) return;
    if (prompt("Type DELETE to confirm:") !== "DELETE") return;
    if (!confirm("Delete ALL sales before " + date + "? Tax records will be KEPT.")) return;
    try {
        const result = await apiCall("/sales/delete-before/" + date, "DELETE");
        showSuccess(result.message);
        await loadAllSales();
        await loadReceiptHistory();
    } catch (err) {
        showError(err);
    }
}


// ============================================================
//  Part 4 event wiring
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    const wire = (id, handler) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("submit", singleSubmit(handler));
    };

    wire("userForm", saveUser);
    wire("editUserForm", saveEditedUser);
    wire("poForm", savePO);

    // Restore file input — nothing to wire, handled in functions
});



// ============================================================
//  Printer Configuration
// ============================================================

async function loadPrinters() {
    const status = document.getElementById("printerStatus");
    const receiptSel = document.getElementById("receiptPrinterSelect");
    const reportSel = document.getElementById("reportPrinterSelect");

    if (!receiptSel || !reportSel) return;

    status.textContent = "Detecting printers...";
    status.style.color = "#666";

    try {
        const data = await apiCall("/printers/available");

        const printers = data.printers || [];
        if (printers.length === 0) {
            status.textContent = "No printers found on this machine.";
            status.style.color = "#d32f2f";
            return;
        }

        // Load current config to pre-select
        let current = { receipt_printer: "", report_printer: "" };
        try {
            current = await apiCall("/printers/config");
        } catch (e) { /* ignore */ }

        // Build dropdowns
        const buildOptions = (selected) =>
            "<option value=\"\">-- Select Printer --</option>" +
            printers.map(p =>
                "<option value=\"" + p + "\"" + (p === selected ? " selected" : "") + ">" + p + "</option>"
            ).join("");

        receiptSel.innerHTML = buildOptions(current.receipt_printer);
        reportSel.innerHTML = buildOptions(current.report_printer);

        status.textContent = "Found " + printers.length + " printer(s). Default: " + (data.default || "none");
        status.style.color = "#2e7d32";
    } catch (e) {
        status.textContent = "Error detecting printers: " + e.message;
        status.style.color = "#d32f2f";
    }
}

async function loadPrinterSettings() {
    try {
        const config = await apiCall("/printers/config");
        const pdfInput = document.getElementById("pdfFallbackFolder");
        const autoReceipt = document.getElementById("autoPrintReceipt");
        const autoReport = document.getElementById("autoPrintReport");

        if (pdfInput) pdfInput.value = config.pdf_fallback_folder || "";
        if (autoReceipt) autoReceipt.checked = (config.auto_print_receipt !== "false");
        if (autoReport) autoReport.checked = (config.auto_print_report === "true");

        // Also populate dropdowns if printers are already configured
        const receiptSel = document.getElementById("receiptPrinterSelect");
        const reportSel = document.getElementById("reportPrinterSelect");
        if (receiptSel && config.receipt_printer) {
            if (!receiptSel.querySelector("option[value=\"" + config.receipt_printer + "\"]")) {
                const opt = document.createElement("option");
                opt.value = config.receipt_printer;
                opt.textContent = config.receipt_printer;
                receiptSel.appendChild(opt);
            }
            receiptSel.value = config.receipt_printer;
        }
        if (reportSel && config.report_printer) {
            if (!reportSel.querySelector("option[value=\"" + config.report_printer + "\"]")) {
                const opt = document.createElement("option");
                opt.value = config.report_printer;
                opt.textContent = config.report_printer;
                reportSel.appendChild(opt);
            }
            reportSel.value = config.report_printer;
        }
    } catch (e) {
        console.error("[loadPrinterSettings]", e);
    }
}

async function savePrinterSettings() {
    const receiptSel = document.getElementById("receiptPrinterSelect");
    const reportSel = document.getElementById("reportPrinterSelect");
    const pdfInput = document.getElementById("pdfFallbackFolder");
    const autoReceipt = document.getElementById("autoPrintReceipt");
    const autoReport = document.getElementById("autoPrintReport");
    const status = document.getElementById("printerStatus");

    const payload = {
        receipt_printer: receiptSel ? receiptSel.value : "",
        report_printer: reportSel ? reportSel.value : "",
        pdf_fallback_folder: pdfInput ? pdfInput.value : "",
        auto_print_receipt: autoReceipt && autoReceipt.checked ? "true" : "false",
        auto_print_report: autoReport && autoReport.checked ? "true" : "false",
    };

    try {
        await apiCall("/printers/config", "PUT", payload);
        if (status) {
            status.textContent = "Printer settings saved.";
            status.style.color = "#2e7d32";
        }
        showSuccess("Printer settings saved");
    } catch (e) {
        if (status) {
            status.textContent = "Save failed: " + e.message;
            status.style.color = "#d32f2f";
        }
        showError(e);
    }
}



// ============================================================
//  Print Queue UI
// ============================================================

let pqAutoRefresh = null;

async function loadPrintQueue() {
    try {
        const data = await apiCall("/print-queue/summary");

        const counts = data.counts || {};
        document.getElementById("pqPending").textContent = counts.pending || 0;
        document.getElementById("pqPrinting").textContent = counts.printing || 0;
        document.getElementById("pqPrinted").textContent = counts.printed || 0;
        document.getElementById("pqFailed").textContent = counts.failed || 0;

        const tbody = document.getElementById("pqTableBody");
        const recent = data.recent || [];

        if (recent.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"7\" style=\"color:#2e7d32\">No print jobs yet</td></tr>";
        } else {
            tbody.innerHTML = recent.map(j => {
                const statusColors = {
                    "pending":  "#ffc107",
                    "printing": "#0088cc",
                    "printed":  "#2e7d32",
                    "failed":   "#d32f2f"
                };
                const color = statusColors[j.status] || "#666";

                let actionCell = "";
                if (j.status === "failed") {
                    actionCell = "<button onclick=\"retryPrintJob(" + j.id + ")\" style=\"padding:3px 10px;font-size:11px;background:#2e7d32;color:white;border:none;border-radius:3px;cursor:pointer;margin-right:5px\">Retry</button>" +
                                 "<span style=\"color:#d32f2f;font-size:11px\">" + (j.error_message || "").substring(0, 60) + "</span>";
                } else {
                    actionCell = "-";
                }

                return "<tr><td>" + j.id + "</td><td>" + j.job_type + "</td>" +
                    "<td style=\"color:" + color + ";font-weight:bold\">" + j.status.toUpperCase() + "</td>" +
                    "<td>" + j.printer_name + "</td>" +
                    "<td>" + j.created_at + "</td>" +
                    "<td>" + (j.printed_at || "-") + "</td>" +
                    "<td>" + actionCell + "</td></tr>";
            }).join("");
        }

        const ts = new Date().toLocaleTimeString();
        document.getElementById("pqLastUpdated").textContent = "Last updated: " + ts;
    } catch (e) {
        console.error("[loadPrintQueue]", e);
    }
}

async function sendTestPrint() {
    try {
        const result = await apiCall("/print-queue/test", "POST", {});
        showSuccess("Test job queued as #" + result.job_id + " -> " + result.printer_name);
        setTimeout(loadPrintQueue, 2000);
    } catch (e) {
        showError(e);
    }
}

async function clearPrintedJobs() {
    if (!confirm("Remove all printed jobs from the queue?")) return;
    try {
        const result = await apiCall("/print-queue/clear-printed", "POST");
        showSuccess("Removed " + result.removed + " job(s)");
        loadPrintQueue();
    } catch (e) {
        showError(e);
    }
}

async function retryPrintJob(jobId) {
    try {
        await apiCall("/print-queue/retry/" + jobId, "POST");
        showSuccess("Job #" + jobId + " re-queued");
        setTimeout(loadPrintQueue, 2000);
    } catch (e) {
        showError(e);
    }
}

function startPrintQueueAutoRefresh() {
    if (pqAutoRefresh) clearInterval(pqAutoRefresh);
    pqAutoRefresh = setInterval(() => {
        const view = document.getElementById("printQueue");
        if (view && view.style.display !== "none") {
            loadPrintQueue();
        }
    }, 5000);
}



// ============================================================
//  Report Push-to-Print
// ============================================================

function _reportHtmlHeader(title) {
    const bs = businessSettings || {};
    return "<div style='text-align:center;border-bottom:2px solid #000;padding-bottom:10px;margin-bottom:15px'>" +
        "<h1 style='margin:0;font-size:20px'>" + (bs.business_name || "Safari POS Pro") + "</h1>" +
        "<p style='margin:4px 0;font-size:11px'>" +
        [(bs.business_po_box || ""), (bs.business_location || "")].filter(Boolean).join(", ") +
        "</p>" +
        "<p style='margin:4px 0;font-size:11px'>" +
        (bs.business_phone ? "Tel: " + bs.business_phone : "") +
        (bs.business_tax_pin ? " | PIN: " + bs.business_tax_pin : "") +
        "</p>" +
        "<h2 style='margin:10px 0 0 0;font-size:16px;text-transform:uppercase'>" + title + "</h2>" +
        "<p style='margin:4px 0;font-size:11px'>Generated: " +
        new Date().toLocaleString() + "</p>" +
        "</div>";
}

function _reportHtmlFooter() {
    const user = authManager.getUser();
    return "<div style='margin-top:20px;padding-top:10px;border-top:1px solid #ccc;font-size:10px;text-align:center'>" +
        "Printed by: " + (user ? user.name : "N/A") + " | Safari POS Pro v4.0 | From Vision to Version" +
        "</div>";
}

function _wrapReport(title, bodyHtml) {
    return "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>" + title + "</title>" +
        "<style>" +
        "body{font-family:Arial,sans-serif;padding:20px;color:#222}" +
        "table{width:100%;border-collapse:collapse;font-size:11px;margin-top:10px;table-layout:fixed}td,th{word-wrap:break-word;overflow-wrap:break-word}" +
        "th,td{border:1px solid #999;padding:6px;text-align:left}" +
        "th{background:#8b4513;color:white}" +
        "tr:nth-child(even){background:#f9f9f9}" +
        ".total-row{font-weight:bold;background:#f5e6d3}" +
        "</style></head><body>" +
        _reportHtmlHeader(title) +
        bodyHtml +
        _reportHtmlFooter() +
        "</body></html>";
}

async function printReport(reportType) {
    try {
        let payload = "";
        let title = "";

        if (reportType === "daily-close") {
            const data = await apiCall("/sales/daily-close");
            title = "Daily Close Report";
            payload = _wrapReport(title,
                "<p><strong>Date:</strong> " + data.date + "</p>" +
                "<table><tr><th>Payment Method</th><th>Total</th></tr>" +
                "<tr><td>Cash</td><td>KSh " + data.cash_total.toFixed(2) + "</td></tr>" +
                "<tr><td>M-Pesa</td><td>KSh " + data.mpesa_total.toFixed(2) + "</td></tr>" +
                "<tr><td>Card</td><td>KSh " + data.card_total.toFixed(2) + "</td></tr>" +
                "<tr class='total-row'><td>GRAND TOTAL</td><td>KSh " + data.grand_total.toFixed(2) + "</td></tr>" +
                "</table>" +
                "<p style='margin-top:15px'><strong>Total Transactions:</strong> " + data.total_transactions + "</p>"
            );
        } else if (reportType === "profit") {
            const data = await apiCall("/reports/profit");
            title = "Profit Report";
            let rows = "";
            data.forEach(p => {
                rows += "<tr><td>" + p.product + "</td><td>KSh " + p.selling_price + "</td>" +
                    "<td>" + p.tax_rate + "%</td><td>KSh " + p.net_selling + "</td>" +
                    "<td>KSh " + (p.cost || 0) + "</td><td>KSh " + p.gross_profit + "</td>" +
                    "<td>" + p.profit_margin + "%</td></tr>";
            });
            payload = _wrapReport(title,
                "<table><tr><th>Product</th><th>Selling</th><th>Tax</th><th>Net</th><th>Cost</th><th>Profit</th><th>Margin</th></tr>" +
                (rows || "<tr><td colspan='7'>No data</td></tr>") + "</table>"
            );
        } else if (reportType === "sales") {
            const data = await apiCall("/sales/all");
            title = "All Sales Report";
            let rows = "";
            let total = 0;
            data.forEach(s => {
                total += s.total_amount;
                rows += "<tr><td>" + s.receipt_no + "</td><td>" + s.created_at + "</td>" +
                    "<td>" + s.cashier + "</td><td>" + s.payment_method.toUpperCase() + "</td>" +
                    "<td>KSh " + s.total_amount.toFixed(2) + "</td></tr>";
            });
            payload = _wrapReport(title,
                "<table><tr><th>Receipt</th><th>Date</th><th>Cashier</th><th>Payment</th><th>Total</th></tr>" +
                (rows || "<tr><td colspan='5'>No sales</td></tr>") +
                "<tr class='total-row'><td colspan='4'>TOTAL</td><td>KSh " + total.toFixed(2) + "</td></tr>" +
                "</table>"
            );
        } else if (reportType === "analytics") {
            const data = await apiCall("/analytics/overview");
            title = "Analytics Overview";
            let html = "<h3 style='color:#8b4513;font-size:14px;margin-top:20px'>Top Sellers</h3>";
            html += "<table><tr><th>#</th><th>Product</th><th>Qty</th><th>Revenue</th></tr>";
            (data.top_sellers || []).forEach((t, i) => {
                html += "<tr><td>" + (i+1) + "</td><td>" + t.name + "</td><td>" + t.qty + "</td><td>KSh " + t.revenue.toFixed(2) + "</td></tr>";
            });
            html += "</table>";
            html += "<h3 style='color:#8b4513;font-size:14px;margin-top:20px'>Profit Champions</h3>";
            html += "<table><tr><th>#</th><th>Product</th><th>Profit</th><th>Margin</th></tr>";
            (data.profit_champions || []).forEach((t, i) => {
                html += "<tr><td>" + (i+1) + "</td><td>" + t.name + "</td><td>KSh " + t.profit.toFixed(2) + "</td><td>" + t.margin + "%</td></tr>";
            });
            html += "</table>";
            payload = _wrapReport(title, html);
        } else if (reportType === "tax") {
            const data = await apiCall("/tax/summary");
            title = "Tax Collection Summary";
            payload = _wrapReport(title,
                "<table><tr><th>Period</th><th>Tax Collected</th></tr>" +
                "<tr><td>Today</td><td>KSh " + data.today_tax.toFixed(2) + "</td></tr>" +
                "<tr><td>This Month</td><td>KSh " + data.month_tax.toFixed(2) + "</td></tr>" +
                "<tr><td>This Year</td><td>KSh " + data.year_tax.toFixed(2) + "</td></tr>" +
                "<tr class='total-row'><td>All Time</td><td>KSh " + data.total_tax.toFixed(2) + "</td></tr>" +
                "</table>"
            );
        } else {
            alert("Unknown report type: " + reportType);
            return;
        }

        const result = await apiCall("/print-queue/enqueue-report", "POST", {
            report_type: reportType,
            title: title,
            payload: payload,
        });

        showSuccess(title + " queued as job #" + result.job_id + " → " + result.printer_name);
    } catch (e) {
        showError(e);
    }
}
