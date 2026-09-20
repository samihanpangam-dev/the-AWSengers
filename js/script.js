/* =========================================================
   INFINITY TOOL BOX
   THE AWSENGERS

   This file handles:

   ✓ Category cards
   ✓ Shared tool catalogue rendering
   ✓ Tool navigation
   ✓ Global search
   ✓ Category filtering
   ✓ Dark / Light mode
   ✓ Mobile navigation
   ✓ Ctrl + K search shortcut
   ✓ URL hash category navigation
========================================================= */


/* =========================================================
   COMPLETE TOOL CATALOGUE
========================================================= */

const CATALOG = window.TOOL_CATALOG;
;


/* =========================================================
   EXISTING TOOLS
========================================================= */

const existing = [

    [
        "PDF Merger",
        "tools/pdf-merger/index.html",
        "📄"
    ],

    [
        "PDF Splitter",
        "tools/pdf-splitter/index.html",
        "✂️"
    ],

    [
        "Image Compressor",
        "tools/image-compressor/index.html",
        "🗜️"
    ],

    [
        "Image Converter",
        "tools/image-converter/index.html",
        "🖼️"
    ]

];


/* =========================================================
   SHORT SELECTORS
========================================================= */

const $ =
    selector =>
        document.querySelector(selector);


const $$ =
    selector =>
        [
            ...document.querySelectorAll(selector)
        ];


/* =========================================================
   TOOL ICON FUNCTION
========================================================= */

function getToolIcon(name) {

    const n =
        name.toLowerCase();


    if (n.includes("pdf"))
        return "📄";


    if (n.includes("image"))
        return "🖼️";


    if (n.includes("json"))
        return "{}";


    if (
        n.includes("csv") ||
        n.includes("data")
    )
        return "📊";


    if (
        n.includes("password") ||
        n.includes("security") ||
        n.includes("hash")
    )
        return "🔐";


    if (
        n.includes("calculator") ||
        n.includes("converter") ||
        n.includes("percentage")
    )
        return "🧮";


    if (
        n.includes("time") ||
        n.includes("date") ||
        n.includes("countdown") ||
        n.includes("stopwatch")
    )
        return "⏱️";


    if (
        n.includes("color") ||
        n.includes("gradient") ||
        n.includes("design")
    )
        return "🎨";


    if (
        n.includes("prompt") ||
        n.includes("ai") ||
        n.includes("research")
    )
        return "🤖";


    if (
        n.includes("ip") ||
        n.includes("url") ||
        n.includes("network")
    )
        return "🌐";


    if (
        n.includes("text") ||
        n.includes("word") ||
        n.includes("writing")
    )
        return "✍️";


    return "🧰";

}


/* =========================================================
   HTML ESCAPE
========================================================= */

function escapeHTML(value) {

    return String(value)
        .replace(
            /[&<>"']/g,
            character => {

                const map = {

                    "&":
                        "&amp;",

                    "<":
                        "&lt;",

                    ">":
                        "&gt;",

                    '"':
                        "&quot;",

                    "'":
                        "&#039;"

                };

                return map[character];

            }
        );

}


/* =========================================================
   PARSE TOOLS
========================================================= */

const parsedCatalog =
    CATALOG.map(category => {

        return {

            ...category,

            tools:
                category.tools.map(tool => {

                    const parts =
                        tool.split("|");

                    return {

                        name:
                            parts[0],

                        url:
                            parts[1]

                    };

                })

        };

    });


/* =========================================================
   PAGE ELEMENTS
========================================================= */

const categoryGrid =
    $("#categoryGrid");


const catalogElement =
    $("#catalog");


const searchInput =
    $("#toolSearch");


const resultCount =
    $("#resultCount");


const navigation =
    $("#navLinks");


/* =========================================================
   RENDER CATEGORY CARDS
========================================================= */

function renderCategories() {

    const visibleCategories =
        parsedCatalog.filter(
            category =>
                category.key !==
                "extra-utilities"
        );


    categoryGrid.innerHTML =
        visibleCategories
            .map(category => {

                return `

                    <button
                        class="category-card"
                        data-target="${category.key}"
                    >

                        <span
                            class="category-icon"
                        >
                            ${category.icon}
                        </span>


                        <span
                            class="category-info"
                        >

                            <strong>
                                ${escapeHTML(
                                    category.name
                                )}
                            </strong>


                            <small>
                                ${escapeHTML(
                                    category.desc
                                )}
                            </small>


                            <em>
                                ${category.tools.length}
                                tools
                            </em>

                        </span>


                        <span class="arrow">
                            →
                        </span>

                    </button>

                `;

            })
            .join("");

}


/* =========================================================
   RENDER TOOL CATALOG
========================================================= */

function renderCatalog() {

    catalogElement.innerHTML =
        parsedCatalog
            .map(category => {

                return `

                    <section
                        class="category-section"
                        id="category-${category.key}"
                    >


                        <div
                            class="category-heading"
                        >

                            <div>

                                <span
                                    class="eyebrow"
                                >
                                    ${category.icon}
                                    CATEGORY
                                </span>


                                <h2>
                                    ${escapeHTML(
                                        category.name
                                    )}
                                </h2>


                                <p>
                                    ${escapeHTML(
                                        category.desc
                                    )}
                                </p>

                            </div>


                            <span
                                class="category-count"
                            >

                                ${category.tools.length}
                                tools

                            </span>

                        </div>



                        <div class="tool-grid">

                            ${

                                category.tools

                                    .map(tool => {

                                        return `

                                            <a
                                                class="tool-card"
                                                href="${escapeHTML(
                                                    tool.url
                                                )}"
                                            >

                                                <span
                                                    class="tool-icon"
                                                >
                                                    ${getToolIcon(
                                                        tool.name
                                                    )}
                                                </span>


                                                <span
                                                    class="tool-copy"
                                                >

                                                    <strong>
                                                        ${escapeHTML(
                                                            tool.name
                                                        )}
                                                    </strong>


                                                    <small>
                                                        Open this
                                                        tool and
                                                        start working.
                                                    </small>

                                                </span>


                                                <span
                                                    class="tool-arrow"
                                                >
                                                    ↗
                                                </span>

                                            </a>

                                        `;

                                    })

                                    .join("")

                            }

                        </div>


                    </section>

                `;

            })

            .join("");

}


/* =========================================================
   GO TO CATEGORY
========================================================= */

function goToCategory(key) {

    const category =
        document.getElementById(
            `category-${key}`
        );


    if (!category)
        return;


    history.replaceState(
        null,
        "",
        `#category-${key}`
    );


    const top =
        category.getBoundingClientRect().top
        +
        window.scrollY
        -
        90;


    window.scrollTo({

        top,

        behavior:
            "smooth"

    });

}


/* =========================================================
   CATEGORY CLICK
========================================================= */

categoryGrid.addEventListener(
    "click",
    event => {

        const card =
            event.target.closest(
                "[data-target]"
            );


        if (!card)
            return;


        goToCategory(
            card.dataset.target
        );

    }
);


/* =========================================================
   GLOBAL SEARCH
========================================================= */

searchInput.addEventListener(
    "input",
    () => {

        const query =
            searchInput.value
                .trim()
                .toLowerCase();


        let visibleTools = 0;


        $$(".category-section")
            .forEach(section => {

                let sectionHasResults =
                    false;


                $$(".tool-card", section)
                    .forEach(card => {

                        const matches =
                            !query ||
                            card.textContent
                                .toLowerCase()
                                .includes(query);


                        card.hidden =
                            !matches;


                        if (matches) {

                            visibleTools++;

                            sectionHasResults =
                                true;

                        }

                    });


                section.hidden =
                    !sectionHasResults;

            });


        resultCount.textContent =
            query
                ? visibleTools
                : String(CATALOG.reduce((total, category) => total + category.tools.length, 0));


        if (query) {

            $("#tools")
                .scrollIntoView({

                    behavior:
                        "smooth",

                    block:
                        "start"

                });

        }

    }
);


/* =========================================================
   NAVIGATION LINKS
========================================================= */

$$("[data-scroll]")
    .forEach(link => {

        link.addEventListener(
            "click",
            event => {

                event.preventDefault();


                const target =
                    document.getElementById(
                        link.dataset.scroll
                    );


                if (!target)
                    return;


                target.scrollIntoView({

                    behavior:
                        "smooth"

                });


                navigation
                    .classList
                    .remove("open");

            }
        );

    });


/* =========================================================
   MOBILE MENU
========================================================= */

const menuButton =
    $("#menuToggle");


menuButton.addEventListener(
    "click",
    () => {

        const isOpen = navigation.classList.toggle("open");
        menuButton.setAttribute("aria-expanded", String(isOpen));

    }
);

navigation.addEventListener("click", event => {
    if (event.target.closest("a")) {
        navigation.classList.remove("open");
        menuButton.setAttribute("aria-expanded", "false");
    }
});


/* =========================================================
   THEME
========================================================= */

const themeButton =
    $("#themeToggle");


function updateThemeButton() {

    themeButton.textContent =
        document.body.classList.contains(
            "light"
        )

            ? "☀️ Light"

            : "🌙 Dark";

}


if (
    localStorage.getItem(
        "itbTheme"
    ) === "light"
) {

    document.body
        .classList
        .add("light");

}


updateThemeButton();


themeButton.addEventListener(
    "click",
    () => {

        document.body
            .classList
            .toggle("light");


        const isLight =
            document.body
                .classList
                .contains("light");


        localStorage.setItem(

            "itbTheme",

            isLight
                ? "light"
                : "dark"

        );


        updateThemeButton();

    }
);


/* =========================================================
   CTRL + K SEARCH
========================================================= */

document.addEventListener(
    "keydown",
    event => {

        if (

            (event.ctrlKey ||
             event.metaKey)

            &&

            event.key.toLowerCase()
                === "k"

        ) {

            event.preventDefault();

            searchInput.focus();

        }

    }
);


/* =========================================================
   INITIALIZE
========================================================= */

renderCategories();

renderCatalog();


/* =========================================================
   OPEN CATEGORY FROM URL HASH
========================================================= */

const hash =
    location.hash.match(
        /^#category-(.+)$/
    );


if (
    hash &&
    document.getElementById(
        `category-${hash[1]}`
    )
) {

    setTimeout(
        () => {

            goToCategory(
                hash[1]
            );

        },

        100

    );

}