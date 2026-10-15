const copy = value => ({...value});
const equal = (left, right) => JSON.stringify(left) === JSON.stringify(right);

export class EditorDrafts {
  #entries = new Map();
  #version = 0;

  sync(key, saved) {
    let entry = this.#entries.get(key);
    if (!entry) {
      entry = {saved: copy(saved), value: copy(saved), version: ++this.#version, error: ''};
      this.#entries.set(key, entry);
    } else if (!equal(entry.saved, saved)) {
      if (equal(entry.value, entry.saved)) {
        entry.value = copy(saved);
        entry.version = ++this.#version;
        entry.error = '';
      }
      entry.saved = copy(saved);
    }
    return this.read(key);
  }

  read(key) {
    const entry = this.#entries.get(key);
    return {value: copy(entry.value), version: entry.version, error: entry.error};
  }

  change(key, value) {
    const entry = this.#entries.get(key);
    entry.value = copy(value);
    entry.version = ++this.#version;
    entry.error = '';
  }

  dirty(key) {
    const entry = this.#entries.get(key);
    return Boolean(entry && !equal(entry.value, entry.saved));
  }

  capture(key) {
    return {key, ...this.read(key)};
  }

  accept(submitted) {
    const entry = this.#entries.get(submitted.key);
    if (!entry || entry.version !== submitted.version) return false;
    this.#entries.delete(submitted.key);
    return true;
  }

  setError(key, message, version) {
    const entry = this.#entries.get(key);
    if (!entry || (version !== undefined && entry.version !== version)) return false;
    entry.error = message;
    return true;
  }

  discard(key) {
    const entry = this.#entries.get(key);
    this.change(key, entry.saved);
  }
}
