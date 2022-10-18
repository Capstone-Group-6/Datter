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

	document.documentElement.ondrop = dropHandler;
	document.documentElement.ondragover = dragOverHandler;
})();
