const CO_AUTHOR = /^Co-authored-by:\s*(.+?)\s*<([^>]+)>\s*$/gim;
const GITHUB_NOREPLY = /^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$/i;
const MAINTAINERS = new Set(["GUYARD Marc", "mguyard"]);
// Only people are credited, never assistants or bots.
const NOT_A_PERSON = [
  /@anthropic\.com$/i,
  /@openai\.com$/i,
  /@cursor\.com$/i,
  /^(?:\d+\+)?Copilot@users\.noreply\.github\.com$/i,
  /\[bot\]@users\.noreply\.github\.com$/i,
];

// A GitHub login when the noreply address reveals it, the name otherwise,
// never the e-mail address.
function credit({ name, email }) {
  if (!name || !email || NOT_A_PERSON.some((pattern) => pattern.test(email))) {
    return null;
  }
  const login = email.match(GITHUB_NOREPLY)?.[1];
  if (MAINTAINERS.has(name) || MAINTAINERS.has(login)) {
    return null;
  }
  return login ? `@${login}` : name;
}

function credits(commit) {
  const message = [commit.body, commit.footer].filter(Boolean).join("\n");
  const author = commit.author ? credit(commit.author) : null;
  const coAuthors = [...message.matchAll(CO_AUTHOR)]
    .map(([, name, email]) => credit({ name, email }))
    .filter((person) => person && person !== author);
  return [
    author && `by ${author}`,
    coAuthors.length > 0 && `co-authored by ${[...new Set(coAuthors)].join(", ")}`,
  ].filter(Boolean);
}

module.exports = {
  branches: [
    "main",
    {
      name: "beta",
      prerelease: true,
    },
  ],
  plugins: [
    "@semantic-release/commit-analyzer",
    [
      "@semantic-release/release-notes-generator",
      {
        writerOpts: {
          // A rendering hook only: as notes, the trailers would make
          // commit-analyzer treat every co-authored commit as breaking.
          finalizeContext(context) {
            for (const group of context.commitGroups ?? []) {
              for (const commit of group.commits) {
                const people = credits(commit);
                if (people.length > 0) {
                  commit.subject = `${commit.subject} (${people.join(", ")})`;
                }
              }
            }
            return context;
          },
        },
      },
    ],
    [
      "@semantic-release/changelog",
      {
        changelogFile: "CHANGELOG.md",
      },
    ],
    [
      "semantic-release-replace-plugin",
      {
        replacements: [
          {
            files: ["custom_components/diagral/manifest.json"],
            from: '"version": ".*"',
            to: '"version": "${nextRelease.version}"',
          },
        ],
      },
    ],
    "@semantic-release/github",
    [
      "@semantic-release/git",
      {
        message:
          "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}",
        assets: ["CHANGELOG.md", "custom_components/diagral/manifest.json"],
      },
    ],
  ],
};
