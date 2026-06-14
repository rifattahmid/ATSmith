# Agency And Client Posting Handling Design

## Purpose

ATSmith should handle job postings made by recruiters, HR firms, or agencies on behalf of another company without confusing the posting firm with the actual employer.

Normal direct-employer postings must keep existing behavior.

## Current Problem

The scraper currently extracts a single `company` value. That value is used for both output folder naming and cover-letter language. For agency postings, those two meanings can diverge:

- The posting firm may be the recruiting agency.
- The actual employer may be a named or unnamed client.
- If the client is unnamed, the cover letter should not describe the recruiter as the operating company.

## Posting Contexts

The scraper should classify postings into one of three contexts:

- `direct_employer`: the role is for the posting company itself.
- `agency_for_named_client`: the posting is by an agency/recruiter and the client company name is known.
- `agency_for_unknown_client`: the posting is by an agency/recruiter and the client company name is not known.

Agency detection should be based on posting language such as "our client", "on behalf of our client", "confidential client", "we are recruiting for", or similar third-party wording. A recruitment or HR company hiring for itself should remain `direct_employer` unless the posting implies a third-party client.

## Data Model

The scraper should keep the existing `company` field and add optional fields:

```json
{
  "company": "Client Name or Posting Firm",
  "posting_company": "Recruiting Firm or null",
  "posting_context": "direct_employer | agency_for_named_client | agency_for_unknown_client",
  "client_company": "Client Name or null",
  "cover_letter_company_reference": "Client Name or your client"
}
```

For direct postings, missing fields should default safely to `direct_employer`.

For agency postings with a named client, `company` should be the client name so the output folder is `Client Name - Title`.

For agency postings with an unknown client, `company` should be the recruiting firm so the output folder is `Recruiting Firm - Title`, while `cover_letter_company_reference` should be `your client`.

## User Review

The CLI should show enough context for the operator to catch errors:

```text
Company:  Robert Walters
Posting:  agency for unnamed client
```

If the scraper identifies a named client, the review should make that clear:

```text
Company:  Acme Energy
Posted by: Robert Walters
Posting:  agency for named client
```

Existing title/company/category edit flow can remain. For `agency_for_unknown_client`, editing `company` means editing the posting or recruiting firm used for folder naming. It should not make the cover letter treat that firm as the employer. A later improvement may add explicit editing for posting context, but the first implementation can keep scope narrow.

## Cover Letter Behavior

`generator.py` should derive the cover-letter company reference separately from output folder naming.

Direct employer:

- Cover letter uses the company name normally.
- Company and sector-specific language is allowed when supported by the posting.

Agency for named client:

- Cover letter uses the client name normally.
- Company and sector-specific language is allowed when supported by the posting.

Agency for unknown client:

- Cover letter uses "your client", "your client firm", or "the client organisation" naturally.
- Cover letter should not claim facts about the recruiter as if it were the employer.
- Company/sector-specific fills should be conservative when the client industry, business model, or company context is not in the posting.
- Role/function-specific language remains allowed.

## Error Handling And Defaults

If new fields are absent, malformed, or unknown, ATSmith should behave like the current direct-employer flow.

If the scraper says `agency_for_named_client` but no client name is present, downgrade to `agency_for_unknown_client`.

If the scraper says `agency_for_unknown_client`, do not ask for the client name automatically in the first implementation. The operator can still edit `company` manually if the posting or recruiting firm name is wrong or unknown, but doing so changes output folder naming only. The cover letter should still use the client reference.

## Testing

Add tests for:

- Direct employer postings still use the extracted company normally.
- Agency wording with a named client sets `company` to the client and `posting_company` to the recruiter.
- Agency wording with an unnamed client keeps `company` as the recruiter and uses `your client` in cover-letter prompts.
- A recruitment firm hiring for itself is treated as `direct_employer` if no third-party client language appears.
- Cover-letter prompts for unknown-client postings avoid recruiter-specific company claims.
