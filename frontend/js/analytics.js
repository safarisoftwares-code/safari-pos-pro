// ============================================================
//  Safari POS Pro - Analytics
// ============================================================

async function loadAnalytics() {
    try {
        const data = await apiCall("/analytics/overview");

        // Top Sellers
        const top = data.top_sellers.map((item, i) =>
            "<tr><td>" + (i + 1) + "</td><td>" + item.name + "</td><td>" +
            item.qty + "</td><td>KSh " + item.revenue.toFixed(2) + "</td></tr>"
        ).join("") || "<tr><td colspan=\"4\">No sales yet</td></tr>";
        const topBody = document.getElementById("topSellersBody");
        if (topBody) topBody.innerHTML = top;

        // Worst Sellers
        const worst = data.worst_sellers.map((item, i) =>
            "<tr><td>" + (i + 1) + "</td><td>" + item.name + "</td><td>" +
            item.qty + "</td><td>KSh " + item.revenue.toFixed(2) + "</td></tr>"
        ).join("") || "<tr><td colspan=\"4\">No sales yet</td></tr>";
        const worstBody = document.getElementById("worstSellersBody");
        if (worstBody) worstBody.innerHTML = worst;

        // Profit Champions
        const champs = data.profit_champions.map((item, i) =>
            "<tr><td>" + (i + 1) + "</td><td>" + item.name +
            "</td><td style=\"color:#2e7d32\">KSh " + item.profit.toFixed(2) +
            "</td><td>" + item.margin + "%</td></tr>"
        ).join("") || "<tr><td colspan=\"4\">No cost data</td></tr>";
        const champsBody = document.getElementById("profitChampionsBody");
        if (champsBody) champsBody.innerHTML = champs;

        // Loss Makers
        const loss = data.loss_makers.map((item, i) =>
            "<tr><td>" + (i + 1) + "</td><td>" + item.name +
            "</td><td style=\"color:#d32f2f\">KSh " + item.profit.toFixed(2) +
            "</td><td>" + item.margin + "%</td></tr>"
        ).join("") || "<tr><td colspan=\"4\" style=\"color:#2e7d32\">No loss makers!</td></tr>";
        const lossBody = document.getElementById("lossMakersBody");
        if (lossBody) lossBody.innerHTML = loss;

        // Slow Movers
        const slow = data.slow_movers.map((item, i) =>
            "<tr><td>" + (i + 1) + "</td><td>" + item.name + "</td><td>" +
            item.stock + "</td><td>" + item.sold_30days + "</td></tr>"
        ).join("") || "<tr><td colspan=\"4\">No slow movers</td></tr>";
        const slowBody = document.getElementById("slowMoversBody");
        if (slowBody) slowBody.innerHTML = slow;

    } catch (e) {
        console.error("Analytics error:", e);
    }
}

async function loadExpiryReport() {
    try {
        const data = await apiCall("/analytics/expiry");

        // Expired
        let expiredHtml = "";
        if (data.expired && data.expired.length > 0) {
            data.expired.forEach(item => {
                expiredHtml += "<div style=\"padding:10px;background:#f8d7da;margin-bottom:5px;border-radius:5px;border-left:4px solid #d32f2f\"><strong>" +
                    item.name + "</strong><br>EXPIRED " + Math.abs(item.days) +
                    " days ago<br>Stock: " + item.stock + " units</div>";
            });
        } else {
            expiredHtml = "<p style=\"color:#2e7d32\">No expired items!</p>";
        }
        const expiredEl = document.getElementById("expiredList");
        if (expiredEl) expiredEl.innerHTML = expiredHtml;

        // Expiring soon
        let expiringHtml = "";
        if (data.expiring_soon && data.expiring_soon.length > 0) {
            data.expiring_soon.forEach(item => {
                expiringHtml += "<div style=\"padding:10px;background:#fff3cd;margin-bottom:5px;border-radius:5px;border-left:4px solid #ffc107\"><strong>" +
                    item.name + "</strong><br>Expires in: " + item.days +
                    " days<br>Stock: " + item.stock + " units</div>";
            });
        } else {
            expiringHtml = "<p style=\"color:#2e7d32\">No expiring items!</p>";
        }
        const expiringEl = document.getElementById("expiringList");
        if (expiringEl) expiringEl.innerHTML = expiringHtml;

    } catch (e) {
        console.error("Expiry error:", e);
    }
}
