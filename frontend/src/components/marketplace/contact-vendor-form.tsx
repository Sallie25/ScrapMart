
"use client";

import { useState, type FormEvent } from "react";

type ContactVendorFormProps = {
  vendorName: string;
  listingTitle: string;
};

export function ContactVendorForm({
  vendorName,
  listingTitle,
}: ContactVendorFormProps) {
  const [message, setMessage] = useState(
    `Hello ${vendorName}, I am interested in ${listingTitle}. Is it available?`,
  );
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!message.trim()) {
      return;
    }

    setSubmitted(true);
  }

  return (
    <div className="rounded-2xl border border-border bg-white p-5">
      <h2 className="text-lg font-semibold text-text">Contact vendor</h2>

      <p className="mt-2 text-sm leading-6 text-muted">
        Ask about availability, quantity, material condition, or collection.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <label
          htmlFor="vendor-message"
          className="block text-sm font-medium text-text"
        >
          Your message
        </label>

        <textarea
          id="vendor-message"
          rows={5}
          required
          maxLength={1000}
          value={message}
          onChange={(event) => {
            setMessage(event.target.value);
            setSubmitted(false);
          }}
          className="w-full rounded-lg border border-border bg-white px-3 py-3 text-sm text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        />

        <button
          type="submit"
          className="w-full rounded-lg bg-primary px-4 py-3 font-semibold text-white transition hover:opacity-90"
        >
          Send message
        </button>
      </form>

      {submitted && (
        <p
          role="status"
          className="mt-4 rounded-lg border border-border bg-background p-3 text-sm text-text"
        >
          Demo interaction completed. No message has been sent to {vendorName};
          backend messaging integration is still required.
        </p>
      )}

      <p className="mt-3 text-xs leading-5 text-muted">
        Prototype only: messages are not saved or delivered to a real vendor.
      </p>
    </div>
  );
}
