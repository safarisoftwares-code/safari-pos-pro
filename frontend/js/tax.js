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



// ============================================================
//  Tax Ledger v2 - Archive UI
// ============================================================

async function loadTaxArchive() {
    try {
        const full = await apiCall("/tax/archive/full");
        document.getElementById("taxLiveTotal").textContent = "KSh " + full.live_tax.toFixed(2);
        document.getElementById("taxArchivedTotal").textContent = "KSh " + full.archived_tax.toFixed(2);
        document.getElementById("taxPurgedTotal").textContent = "KSh " + full.purged_tax.toFixed(2);
        document.getElementById("taxGrandTotal").textContent = "KSh " + full.grand_total.toFixed(2);

        const summary = await apiCall("/tax/archive/summary");
        const tbody = document.getElementById("taxArchiveTableBody");
        if (summary.months && summary.months.length > 0) {
            tbody.innerHTML = summary.months.map(m =>
                "<tr><td>" + m.month + "</td><td>" + m.row_count + "</td>" +
                "<td>KSh " + m.total_tax.toFixed(2) + "</td><td>" + m.archived_at + "</td>" +
                "<td style=\"font-family:monospace;font-size:11px\">" + m.sha256_short + "</td>" +
                "<td><button onclick=\"viewTaxMonth('" + m.month + "')\" style=\"padding:3px 10px;font-size:11px;background:#0088cc;color:white;border:none;border-radius:3px;cursor:pointer\">View</button></td></tr>"
            ).join("");
        } else {
            tbody.innerHTML = "<tr><td colspan=\"5\" style=\"color:#2e7d32\">No archived months yet (all records are within the last 12 months)</td></tr>";
        }
    } catch (e) {
        console.error("[loadTaxArchive]", e);
    }
}

async function verifyTaxChain() {
    const box = document.getElementById("taxChainResult");
    box.innerHTML = "<p style=\"color:#666\">Verifying...</p>";
    try {
        const result = await apiCall("/tax/archive/verify");
        if (result.ok) {
            box.innerHTML = "<div style=\"padding:10px;background:#d4edda;color:#155724;border-radius:5px;border-left:4px solid #2e7d32\">" +
                "Chain intact - " + (result.months_verified || 0) + " month(s) verified</div>";
        } else {
            box.innerHTML = "<div style=\"padding:10px;background:#f8d7da;color:#721c24;border-radius:5px;border-left:4px solid #d32f2f\">" +
                "Chain BROKEN: " + result.message + "</div>";
        }
    } catch (e) {
        box.innerHTML = "<div style=\"padding:10px;background:#f8d7da;color:#721c24;border-radius:5px\">Error: " + e.message + "</div>";
    }
}

async function loadPurgeable() {
    const card = document.getElementById("purgeableCard");
    const list = document.getElementById("purgeableList");
    card.style.display = "block";
    list.innerHTML = "<p style=\"color:#666\">Loading...</p>";
    try {
        const result = await apiCall("/tax/archive/purgeable");
        if (!result.months || result.months.length === 0) {
            list.innerHTML = "<p style=\"color:#2e7d32\">No months are old enough to purge yet (need 5+ years retention).</p>";
            return;
        }
        list.innerHTML = result.months.map(m =>
            "<div style=\"display:flex;justify-content:space-between;align-items:center;padding:10px;background:#fff3cd;margin-bottom:5px;border-radius:5px;border-left:4px solid #d32f2f\">" +
            "<div><strong>" + m.month + "</strong> - " + m.row_count + " rows, KSh " + m.total_tax.toFixed(2) + "</div>" +
            "<button onclick=\"confirmPurge('" + m.month + "')\" style=\"background:#d32f2f;color:white;border:none;padding:6px 14px;border-radius:5px;cursor:pointer\">Purge</button>" +
            "</div>"
        ).join("");
    } catch (e) {
        list.innerHTML = "<p style=\"color:#d32f2f\">Error: " + e.message + "</p>";
    }
}

async function confirmPurge(month) {
    if (prompt("Type PURGE " + month + " to permanently delete this month\'s archived tax records:") !== ("PURGE " + month)) {
        return;
    }
    if (!confirm("FINAL WARNING: This will permanently remove the archive for " + month + ". A manifest record will be kept forever for audit. Continue?")) return;

    try {
        const result = await apiCall("/tax/archive/purge/" + month, "POST");
        alert("Purged " + result.month + "\n" + result.rows_purged + " rows, KSh " + result.total_tax.toFixed(2) + " tax\nSHA-256: " + result.sha256);
        loadTaxArchive();
        loadPurgeable();
    } catch (e) {
        alert("Error: " + e.message);
    }
}

async function loadPurgeHistory() {
    const card = document.getElementById("purgeHistoryCard");
    const tbody = document.getElementById("purgeHistoryTableBody");
    card.style.display = "block";
    tbody.innerHTML = "<tr><td colspan=\"6\">Loading...</td></tr>";
    try {
        const history = await apiCall("/tax/archive/purge-history");
        if (!history || history.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"6\" style=\"color:#2e7d32\">No purges have been performed yet</td></tr>";
            return;
        }
        tbody.innerHTML = history.map(h =>
            "<tr><td>" + h.month + "</td><td>" + h.row_count + "</td><td>KSh " + h.total_tax.toFixed(2) + "</td>" +
            "<td style=\"font-family:monospace;font-size:11px\">" + h.sha256_short + "</td>" +
            "<td>" + h.purged_by + "</td><td>" + h.purged_at + "</td></tr>"
        ).join("");
    } catch (e) {
        tbody.innerHTML = "<tr><td colspan=\"6\" style=\"color:#d32f2f\">Error: " + e.message + "</td></tr>";
    }
}



// ============================================================
//  Tax Archive - View & Export a Single Month
// ============================================================

async function viewTaxMonth(month) {
    document.getElementById("taxMonthTitle").textContent = month;
    document.getElementById("taxMonthInfo").textContent = "Loading...";
    const tbody = document.getElementById("taxMonthTableBody");
    tbody.innerHTML = "<tr><td colspan=\"9\">Loading...</td></tr>";
    document.getElementById("taxMonthExport").innerHTML = "";
    openModal("taxMonthModal");

    try {
        const data = await apiCall("/tax/archive/month/" + month);

        document.getElementById("taxMonthInfo").textContent =
            data.total_rows + " row(s) | Total tax: KSh " + data.total_tax.toFixed(2) +
            " | Archived: " + data.archived_at + " | SHA-256: " + data.sha256_short;

        if (!data.rows || data.rows.length === 0) {
            tbody.innerHTML = "<tr><td colspan=\"9\" style=\"color:#2e7d32\">No rows in this archive</td></tr>";
            return;
        }

        tbody.innerHTML = data.rows.map(r =>
            "<tr><td>" + r.receipt_no + "</td><td>" + r.created_at + "</td>" +
            "<td>" + r.product_name + "</td><td>" + r.quantity + "</td>" +
            "<td>KSh " + r.unit_price.toFixed(2) + "</td><td>" + r.tax_rate + "%</td>" +
            "<td>KSh " + r.tax_amount.toFixed(2) + "</td>" +
            "<td>" + r.payment_method.toUpperCase() + "</td><td>" + r.cashier + "</td></tr>"
        ).join("");

        document.getElementById("taxMonthExport").innerHTML =
            "<button onclick=\"exportTaxMonthCSV('" + month + "')\" style=\"background:#2e7d32;color:white;padding:8px 16px;border:none;border-radius:5px;cursor:pointer\">Export CSV</button>";
    } catch (e) {
        document.getElementById("taxMonthInfo").textContent = "Error: " + e.message;
        tbody.innerHTML = "<tr><td colspan=\"9\" style=\"color:#d32f2f\">" + e.message + "</td></tr>";
    }
}


async function exportTaxMonthCSV(month) {
    try {
        const data = await apiCall("/tax/archive/month/" + month + "?limit=100000");
        let csv = "Receipt,Date,Product,Qty,Unit Price,Tax Rate,Tax Amount,Payment,Cashier\n";
        data.rows.forEach(r => {
            csv += [r.receipt_no, r.created_at, '"' + r.product_name + '"', r.quantity,
                    r.unit_price, r.tax_rate, r.tax_amount, r.payment_method, r.cashier].join(",") + "\n";
        });
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "tax_archive_" + month + ".csv";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        setTimeout(function() {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 1000);
    } catch (e) {
        alert("Export failed: " + e.message);
    }
}
