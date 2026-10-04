// ---------- Couche API : seul endroit qui parle au serveur ----------
const api = {
    async request(url, options = {}) {
        const res = await fetch(url, options);
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.error || `Erreur serveur (${res.status})`);
        }
        return res.status === 204 ? null : res.json();
    },
    list() {
        return this.request("/api/buildings");
    },
    create(data) {
        return this.request("/api/buildings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
    },
    remove(id) {
        return this.request(`/api/buildings/${id}`, { method: "DELETE" });
    }
};

// ---------- Modèle ----------
class Building {
    constructor({ id, title, type, image = "", description, tags = [], link = "" }) {
        this.id = id; // fourni par le serveur
        this.title = title;
        this.type = type;
        this.image = image;
        this.description = description;
        this.tags = tags;
        this.link = link;
    }

    matches(query) {
        const haystack = [this.title, this.type, this.description, ...this.tags]
            .join(" ").toLowerCase();
        return haystack.includes(query.toLowerCase());
    }

    render(onDelete) {
        const card = document.createElement("article");
        card.className = "building-card";
        card.dataset.type = this.type.toLowerCase();

        const media = document.createElement("div");
        media.className = "card-media";
        if (this.image) {
            const img = document.createElement("img");
            img.src = this.image;
            img.alt = this.title;
            img.loading = "lazy";
            img.onerror = () => img.remove(); // retombe sur le fond de secours
            media.append(img);
        }
        media.dataset.initial = this.title.charAt(0).toUpperCase();

        const body = document.createElement("div");
        body.className = "card-body";

        const type = document.createElement("span");
        type.className = "card-type";
        type.textContent = this.type;

        const h2 = document.createElement("h2");
        h2.textContent = this.title;

        const p = document.createElement("p");
        p.textContent = this.description;

        const tags = document.createElement("ul");
        tags.className = "tags";
        this.tags.forEach(t => {
            const li = document.createElement("li");
            li.textContent = t;
            tags.append(li);
        });

        const footer = document.createElement("div");
        footer.className = "card-footer";
        if (this.link) {
            const a = document.createElement("a");
            a.href = this.link;
            a.target = "_blank";
            a.rel = "noopener";
            a.textContent = "En savoir plus";
            footer.append(a);
        }

        const del = document.createElement("button");
        del.type = "button";
        del.className = "delete-btn";
        del.textContent = "Supprimer";
        del.addEventListener("click", () => onDelete(this.id));
        footer.append(del);

        body.append(type, h2, p, tags, footer);
        card.append(media, body);
        return card;
    }
}

// ---------- Contrôleur ----------
class BuildingCatalog {
    constructor() {
        this.container = document.getElementById("cards");
        this.countEl = document.getElementById("count");
        this.dialog = document.getElementById("add-dialog");
        this.form = document.getElementById("add-form");
        this.searchInput = document.getElementById("search");
        this.buildings = [];

        // Filtre par type, lu dans l'adresse : index.html?type=Public
        this.typeFilter = new URLSearchParams(location.search).get("type") || "";
        this.showTypeFilter();

        document.getElementById("open-add").addEventListener("click", () => this.openDialog());
        document.getElementById("cancel-add").addEventListener("click", () => this.closeDialog());
        this.form.addEventListener("submit", e => this.onSubmit(e));
        this.searchInput.addEventListener("input", () => this.render());

        this.refresh();
    }

    showTypeFilter() {
        if (!this.typeFilter) return;

        const label = document.getElementById("filter-label");
        const reset = document.createElement("a");
        reset.href = "index.html";
        reset.textContent = "Tout afficher";
        label.replaceChildren(`Type : ${this.typeFilter} `, reset);
        label.hidden = false;

        // met en évidence l'entrée active du menu déroulant
        document.querySelectorAll(".dropdown-menu a").forEach(a => {
            const type = new URL(a.href).searchParams.get("type");
            if (type && type.toLowerCase() === this.typeFilter.toLowerCase()) a.classList.add("active");
        });
    }

    openDialog() {
        // pré-sélectionne le type affiché dans le formulaire d'ajout
        const select = this.form.elements.type;
        const match = [...select.options].find(o => o.value.toLowerCase() === this.typeFilter.toLowerCase());
        if (match) select.value = match.value;
        this.dialog.showModal();
    }

    async refresh() {
        try {
            this.buildings = (await api.list()).map(d => new Building(d));
            this.render();
        } catch (err) {
            const msg = document.createElement("p");
            msg.className = "empty";
            msg.textContent = "Impossible de charger les bâtiments : " + err.message;
            this.container.replaceChildren(msg);
        }
    }

    async onSubmit(e) {
        e.preventDefault();
        const data = new FormData(this.form);
        const payload = {
            title: String(data.get("title")).trim(),
            type: data.get("type"),
            image: String(data.get("image")).trim(),
            description: String(data.get("description")).trim(),
            tags: String(data.get("tags")).split(",").map(t => t.trim()).filter(Boolean),
            link: String(data.get("link")).trim()
        };

        try {
            const created = await api.create(payload);
            this.buildings.unshift(new Building(created));
            this.render();
            this.closeDialog();
        } catch (err) {
            alert("Ajout impossible : " + err.message);
        }
    }

    closeDialog() {
        this.form.reset();
        this.dialog.close();
    }

    async remove(id) {
        const target = this.buildings.find(b => b.id === id);
        if (!confirm(`Supprimer « ${target ? target.title : "ce bâtiment"} » ?`)) return;
        try {
            await api.remove(id);
            this.buildings = this.buildings.filter(b => b.id !== id);
            this.render();
        } catch (err) {
            alert("Suppression impossible : " + err.message);
        }
    }

    render() {
        const query = this.searchInput.value.trim();
        const wanted = this.typeFilter.toLowerCase();
        const visible = this.buildings.filter(b =>
            (!wanted || b.type.toLowerCase() === wanted) && b.matches(query));

        this.container.replaceChildren(...visible.map(b => b.render(id => this.remove(id))));

        if (visible.length === 0) {
            const empty = document.createElement("p");
            empty.className = "empty";
            empty.textContent = query
                ? `Aucun bâtiment ne correspond à « ${query} ».`
                : this.typeFilter
                    ? `Aucun bâtiment de type « ${this.typeFilter} » pour l'instant.`
                    : "Aucun bâtiment pour l'instant. Utilisez « Ajouter un bâtiment » pour commencer.";
            this.container.append(empty);
        }

        this.countEl.textContent = `${visible.length} bâtiment${visible.length > 1 ? "s" : ""}`;
    }
}

document.addEventListener("DOMContentLoaded", () => new BuildingCatalog());