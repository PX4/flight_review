
function restoreSetting(key) {
	var value = localStorage.getItem(key);
	if (value !== null) {
		var field = $("#"+key)[0];
		if (field.type == 'checkbox'){
			field.checked = (value == 'true');
		} else {
			field.value = value;
		}
		console.log(key+', '+value);
	}
}
function saveSetting(key) {
	var field = $("#"+key)[0];
	if (field.type == 'checkbox'){
		var value = field.checked;
	} else {
		var value = field.value;
	}
	localStorage.setItem(key, value);
	console.log(key+', '+value);
}

function saveSettings() {
	saveSetting('email');
	saveSetting('access');
}

function updateAccess() {
    var access = document.getElementById('access').value;
    var ids = ["flightreport", "personal"];
    ids.forEach((value) => {
        if (value == access) {
            document.getElementById(value).style.display='table-row';
        } else {
            document.getElementById(value).style.display='none';
        }
        });
    document.getElementById('public').value = access == "flightreport" ? "true" : "false";
}

function validateForm() {
    var valid = true;
    var error_html = "";
    if (document.getElementById('access').value == "notset") {
        error_html += "Access, "
        valid = false;
    }
    var email = document.getElementById('email').value;
    if (!email.includes("@") || email.length < 5) { // very simple check
        error_html += "E-Mail, "
        valid = false;
    }
    if (document.getElementById('file').value.length == 0) {
        error_html += "Log File, "
        valid = false;
    }

    // Report
    if (!valid) {
        error_html = "<div><font color='red'>Missing fields: " + error_html.substring(0, error_html.length - 2) + "</font></div";
    }
    document.getElementById('feedback').innerHTML = error_html;

    if (valid) {
        saveSettings();
    }

    return valid;
}


$(function() { // on startup
	restoreSetting('email');
	restoreSetting('access');
	updateAccess();
});

