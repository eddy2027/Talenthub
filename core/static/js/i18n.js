(function () {
  const select = document.getElementById('lang');
  const DEFAULT_LANG = 'en';

  function currentLang() {
    return localStorage.getItem('eddy_lang') || DEFAULT_LANG;
  }

  function applyTranslations(dict) {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (dict[key]) el.textContent = dict[key];
    });
    const titleEl = document.querySelector('title[data-i18n]');
    if (titleEl) {
      const key = titleEl.getAttribute('data-i18n');
      if (dict[key]) titleEl.textContent = dict[key];
    }
  }

  async function load(lang) {
    try {
      const res = await fetch(`/static/lang/${lang}.json`);
      const dict = await res.json();
      applyTranslations(dict);
    } catch (e) {
      if (lang !== DEFAULT_LANG) load(DEFAULT_LANG);
    }
  }

  function init() {
    const lang = currentLang();
    if (select) select.value = lang;
    load(lang);
    if (select) {
      select.addEventListener('change', () => {
        const chosen = select.value;
        localStorage.setItem('eddy_lang', chosen);
        load(chosen);
      });
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
