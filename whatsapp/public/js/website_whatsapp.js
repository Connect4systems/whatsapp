(() => {
  const DEFAULT_NUMBER = "201006676145";
  const DEFAULT_ICON = "/files/WhatsApp.svg.webp";

  const getNumber = () => {
    const configured = window.whatsappNumber || window.c4WhatsAppNumber;
    return String(configured || DEFAULT_NUMBER).replace(/[^\d]/g, "");
  };

  const addFloatingButton = () => {
    if (document.querySelector(".wa-float")) return;

    const number = getNumber();
    if (!number) return;

    const link = document.createElement("a");
    link.className = "wa-float";
    link.href = `https://wa.me/${number}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", "Contact on WhatsApp");

    const image = document.createElement("img");
    image.src = window.whatsappIcon || DEFAULT_ICON;
    image.alt = "WhatsApp";
    image.loading = "lazy";
    image.addEventListener(
      "error",
      () => {
        link.textContent = "WA";
      },
      { once: true }
    );

    link.appendChild(image);
    document.body.appendChild(link);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addFloatingButton);
  } else {
    addFloatingButton();
  }
})();
