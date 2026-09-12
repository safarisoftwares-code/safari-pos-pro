// ============================================================
//  Safari POS Pro - Tax Report
// ============================================================

async function loadTaxReport() {
    try {
        const summary = await apiCall("/tax/summary");
        document.getElementById("todayTax").textContent = "KSh " + summary.today_tax.toFixed(2);
        document.getElementById("monthTax").textContent = "KSh " + summary.month_tax.toFixed(2);
        document.getElementById("yearTax").textContent = "KSh " + summary.year_tax.toFixed(2);
        document.getElementById("totalTax").textContent = "KSh " + summary.total_tax.toFixed(2);

        const transactions = await apiCall("/tax/transactions");
        const tbody = document.getElementById("taxTableBody");
        if (tbody) {
            tbody.innerHTML = transactions.map(t =>
                "<tr><td>" + t.receipt_no + "</td><td>" + t.date + "</td><td>" +
                t.product + "</td><td>" + t.quantity + "</td><td>" + t.tax_rate +
                "%</td><td>KSh " + t.tax_amount.toFixed(2) + "</td><td>" +
                t.payment.toUpperCase() + "</td><td>" + t.cashier + "</td></tr>"
            ).join("") || "<tr><td colspan=\"8\">No tax records yet</td></tr>";
        }
    } catch (e) {
        console.error("Tax error:", e);
    }
}
