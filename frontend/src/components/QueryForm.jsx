import { useState } from "react";

const LANGUAGES = ["English", "Spanish", "French", "German", "Japanese", "Portuguese"];
const CITATION_STYLES = [
  { value: "apa", label: "APA" },
  { value: "mla", label: "MLA" },
];

export default function QueryForm({ onSubmit, disabled }) {
  const [query, setQuery] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("English");
  const [citationStyle, setCitationStyle] = useState("apa");
  const [numSubQuestions, setNumSubQuestions] = useState(4);

  function handleSubmit(event) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    onSubmit({
      query: trimmed,
      target_language: targetLanguage,
      citation_style: citationStyle,
      num_sub_questions: Number(numSubQuestions),
    });
  }

  return (
    <form className="query-form" onSubmit={handleSubmit}>
      <textarea
        className="query-textarea"
        placeholder="What do you want researched? e.g. “Impact of microplastics on marine food webs”"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        disabled={disabled}
        rows={3}
      />

      <div className="query-options">
        <div className="option-field">
          <label className="option-label" htmlFor="language-select">
            Report language
          </label>
          <select
            id="language-select"
            className="option-select"
            value={targetLanguage}
            onChange={(event) => setTargetLanguage(event.target.value)}
            disabled={disabled}
          >
            {LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {language}
              </option>
            ))}
          </select>
        </div>

        <div className="option-field">
          <label className="option-label" htmlFor="citation-select">
            Citation style
          </label>
          <select
            id="citation-select"
            className="option-select"
            value={citationStyle}
            onChange={(event) => setCitationStyle(event.target.value)}
            disabled={disabled}
          >
            {CITATION_STYLES.map((style) => (
              <option key={style.value} value={style.value}>
                {style.label}
              </option>
            ))}
          </select>
        </div>

        <div className="option-field">
          <label className="option-label" htmlFor="subquestions-select">
            Depth
          </label>
          <select
            id="subquestions-select"
            className="option-select"
            value={numSubQuestions}
            onChange={(event) => setNumSubQuestions(event.target.value)}
            disabled={disabled}
          >
            <option value={2}>2 sub-questions</option>
            <option value={4}>4 sub-questions</option>
            <option value={6}>6 sub-questions</option>
          </select>
        </div>
      </div>

      <div className="form-footer">
        <span className="pipeline-preview">plan · search · verify · write · review · cite</span>
        <button className="submit-button" type="submit" disabled={disabled || !query.trim()}>
          {disabled ? "Researching…" : "Begin research"}
        </button>
      </div>
    </form>
  );
}
