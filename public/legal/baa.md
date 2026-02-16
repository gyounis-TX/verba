# Business Associate Agreement

**Version 1.0 — Effective February 2026**

This Business Associate Agreement ("BAA") is entered into by and between you, the healthcare provider or covered entity ("Covered Entity"), and Lumen Innovations LLC, operating the Explify platform ("Business Associate"), effective as of the date of electronic acceptance.

## 1. Definitions

- **HIPAA** means the Health Insurance Portability and Accountability Act of 1996, as amended, including the HITECH Act and all implementing regulations (45 CFR Parts 160 and 164).
- **Protected Health Information (PHI)** means individually identifiable health information as defined in 45 CFR 160.103, including electronic PHI (ePHI).
- **Breach** means the acquisition, access, use, or disclosure of PHI in a manner not permitted under HIPAA that compromises the security or privacy of the PHI, as defined in 45 CFR 164.402.
- **Business Associate** means Lumen Innovations LLC, which creates, receives, maintains, or transmits PHI on behalf of the Covered Entity through the Explify platform.
- **Covered Entity** means the healthcare provider or organization that uses the Explify platform and is subject to HIPAA.
- **Security Incident** means the attempted or successful unauthorized access, use, disclosure, modification, or destruction of information or interference with system operations in an information system, as defined in 45 CFR 164.304.

## 2. How Explify Handles Your Data

Explify is designed with a privacy-first architecture:

- **PHI Scrubbing**: Before any medical report text is sent to an AI language model for explanation, Explify automatically scrubs all personally identifiable health information (names, dates, medical record numbers, and other HIPAA Safe Harbor identifiers). Only de-identified clinical content is transmitted to AI providers.
- **Local Processing**: In desktop mode, all data is stored locally on your device. No PHI is transmitted to Explify servers.
- **Web Mode**: In web mode, report text is transmitted over TLS-encrypted connections to Explify servers for processing. PHI is scrubbed before any AI model interaction. Stored data is encrypted at rest.
- **No Raw PHI in AI Requests**: AI language model providers (e.g., Anthropic, OpenAI) never receive identifiable patient information. They receive only de-identified clinical text.

## 3. Obligations of Business Associate

Business Associate agrees to:

- **Safeguards**: Implement administrative, physical, and technical safeguards that reasonably and appropriately protect the confidentiality, integrity, and availability of ePHI, as required by 45 CFR 164.308, 164.310, and 164.312.
- **Use and Disclosure Limitations**: Not use or disclose PHI other than as permitted or required by this BAA, as required to perform services for the Covered Entity, or as required by law.
- **Minimum Necessary Standard**: Limit the use, disclosure, and request of PHI to the minimum necessary to accomplish the intended purpose, consistent with 45 CFR 164.502(b).
- **Reporting**: Report to the Covered Entity any use or disclosure of PHI not provided for by this BAA of which Business Associate becomes aware, including any Security Incident.
- **Subcontractors**: Ensure that any subcontractors that create, receive, maintain, or transmit PHI on behalf of Business Associate agree to the same restrictions and conditions that apply to Business Associate under this BAA. This includes AI language model providers, cloud infrastructure providers, and any other third-party services.
- **Access to PHI**: Make available PHI in a Designated Record Set to the Covered Entity or the individual as required by 45 CFR 164.524.
- **Amendment of PHI**: Make available PHI for amendment and incorporate any amendments to PHI as required by 45 CFR 164.526.
- **Accounting of Disclosures**: Make available the information required to provide an accounting of disclosures as required by 45 CFR 164.528.
- **Government Access**: Make internal practices, books, and records relating to the use and disclosure of PHI available to the Secretary of the U.S. Department of Health and Human Services for purposes of determining compliance with HIPAA.
- **Encryption**: Encrypt all ePHI in transit (TLS 1.2 or higher) and at rest (AES-256 or equivalent).

## 4. Permitted Uses and Disclosures

Business Associate may use and disclose PHI only as follows:

- To perform services on behalf of the Covered Entity as described in the Explify Terms of Service, including medical report processing, explanation generation, and related analytics.
- To de-identify PHI in accordance with 45 CFR 164.514.
- As required by law.
- For the proper management and administration of the Business Associate, provided that any disclosure is required by law or the Business Associate obtains reasonable assurances that the information will be held confidentially.

## 5. Breach Notification

- Business Associate shall notify the Covered Entity without unreasonable delay, and in no event later than **60 calendar days** after discovery of a Breach of unsecured PHI.
- Notification shall include, to the extent possible: the nature of the Breach, the types of PHI involved, the identity of each individual affected, the steps Business Associate has taken to mitigate the Breach, and contact information for further inquiries.
- Business Associate shall cooperate with the Covered Entity in the investigation and mitigation of any Breach.

## 6. Term and Termination

- **Term**: This BAA shall remain in effect for the duration of the Covered Entity's use of the Explify platform.
- **Termination for Cause**: The Covered Entity may terminate this BAA if it determines that Business Associate has violated a material term of this BAA. Business Associate shall be given 30 days to cure the violation before termination takes effect.
- **Effect of Termination**: Upon termination, Business Associate shall, if feasible, return or destroy all PHI received from, or created or received by Business Associate on behalf of, the Covered Entity. If return or destruction is not feasible, Business Associate shall extend the protections of this BAA to such PHI and limit further uses and disclosures to those purposes that make the return or destruction infeasible.
- **Account Deletion**: The Covered Entity may request deletion of all data at any time through the Explify account settings. Business Associate will process such requests within 30 days.

## 7. Obligations of Covered Entity

Covered Entity agrees to:

- Obtain any necessary consents or authorizations from individuals whose PHI will be provided to Business Associate.
- Not request Business Associate to use or disclose PHI in any manner that would not be permissible under HIPAA.
- Notify Business Associate of any limitations in the Covered Entity's notice of privacy practices that may affect Business Associate's use or disclosure of PHI.

## 8. Miscellaneous

- **Amendment**: This BAA may be amended by Business Associate to comply with changes in HIPAA or other applicable law. Updated versions will be presented for acceptance through the Explify platform.
- **Interpretation**: Any ambiguity in this BAA shall be resolved in favor of a meaning that permits the parties to comply with HIPAA.
- **Governing Law**: This BAA shall be governed by federal HIPAA regulations. To the extent not preempted by federal law, the laws of the State of Texas shall apply.
- **No Third-Party Beneficiaries**: Nothing in this BAA shall confer upon any person other than the parties and their respective successors or assigns any rights, remedies, obligations, or liabilities whatsoever.
- **Survival**: The obligations of Business Associate under Sections 3 and 5 shall survive the termination of this BAA.

## 9. Electronic Acceptance

By clicking "I Accept" below, you acknowledge that you have read, understood, and agree to be bound by the terms of this Business Associate Agreement. This electronic acceptance constitutes a legally binding signature under the Electronic Signatures in Global and National Commerce Act (E-SIGN Act) and the Uniform Electronic Transactions Act (UETA).

Your acceptance is recorded with your user identity, timestamp, IP address, and browser information for compliance purposes.
