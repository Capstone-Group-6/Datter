(function () {
	let isUploading = false

	function dropHandler(ev) {
		ev.preventDefault();

		if (isUploading) return;

		let files;
		if (ev.dataTransfer.items) {
			files = [...ev.dataTransfer.items].filter(item => item.kind === 'file').map(item => item.getAsFile());
		} else {
			files = [...ev.dataTransfer.files];
		}

		if (files.length !== 1) {
			window.alert("Sorry! Only one file is accepted at a time.");
			return;
		}

		const data = new FormData();
		data.append('file', files[0]);

		isUploading = true;
		document.getElementById("uploading").classList.add("show");

		fetch('/data', {
			body: data,
			method: 'POST'
		}).then(res => res.json()).then(res => window.location.href = res.redirect_to);
	}

	function dragOverHandler(ev) {
		ev.preventDefault();
	}

	if (window.username) {
		document.documentElement.ondrop = dropHandler;
		document.documentElement.ondragover = dragOverHandler;
	}
})();

(function () {
	const confirmPassword = document.getElementById("confirm-password");
	if (confirmPassword) {
		const password = document.getElementById("password");

		function validatePassword() {
			if (confirmPassword.value !== password.value) {
				confirmPassword.setCustomValidity("Passwords don't match");
			} else {
				confirmPassword.setCustomValidity("");
			}
		}

		password.onchange = validatePassword;
		confirmPassword.onkeyup = validatePassword;
	}
})();

(function () {
	if (window.username) {
		const logoutLinks = document.querySelectorAll("a[href='/logout']");
		for (const logoutLink of logoutLinks) {
			logoutLink.onclick = e => {
				e.preventDefault();

				const form = document.createElement("form");
				form.method = "post";
				form.action = "/logout";

				document.body.append(form);
				form.submit();
			};
		}
	}
})();

(function () {
	const errorPopup = document.getElementById("error-popup");
	if (errorPopup) {
		errorPopup.onclick = () => errorPopup.remove();
	}
})();


const dropArea = document.querySelector(".drag-area"),
    dragText = dropArea.querySelector("header"),
    button = dropArea.querySelector("button"),
    input = dropArea.querySelector("input");
let file;
button.onclick = () => {
    input.click();
}
input.addEventListener("change", function () {
    file = this.files[0];
    dropArea.classList.add("active");
    showFile();
});
dropArea.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropArea.classList.add("active");
    dragText.textContent = "Release to Upload File";
});

dropArea.addEventListener("dragleave", () => {
    dropArea.classList.remove("active");
    dragText.textContent = "Drag & Drop to Upload File";
});

dropArea.addEventListener("drop", (event) => {
    event.preventDefault();
    file = event.dataTransfer.files[0];
    showFile();
});
function showFile() {
    let fileType = file.type;
    let validExtensions = ["image/jpeg", "image/jpg", "image/png"];
    if (validExtensions.includes(fileType)) {
        let fileReader = new FileReader();
        fileReader.onload = () => {
            let fileURL = fileReader.result;
            let imgTag = `<img src="${fileURL}" alt="image">`;
            dropArea.innerHTML = imgTag;
        }
        fileReader.readAsDataURL(file);
    } else {
        alert("This is not an Image File!");
        dropArea.classList.remove("active");
        dragText.textContent = "Drag & Drop to Upload File";
    }
}