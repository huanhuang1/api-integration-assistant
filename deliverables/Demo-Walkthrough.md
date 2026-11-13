# API Integration Assistant demo script

Hi, I built a small assistant that helps developers find the right API calls for an account-opening scenario. You describe what you want to do, and it shows the API order, the fields to send, and example requests.

*[Click **Personal account** in the Streamlit app.]*

Here I’m asking how to open a USD account for a new individual customer. The guide shows three steps. Create the customer, verify their identity, then create the account once verification passes. It also shows where each value comes from. The currency comes from my question, and the customer ID and verification ID come from the earlier example responses.

*[Expand **Inspect retrieval and backend lookups**.]*

Before the demo, the ingestion step reads OpenAPI specs, workflow definitions, and business rules. It saves the full records as JSON and stores embeddings of workflow descriptions in Chroma.

When I ask a question, the LangChain pipeline searches Chroma for candidate workflows. The local language model extracts details like customer type and currency. Python matches those details to a workflow, looks up the full API specs and rules by ID, and builds examples that it checks against the API schemas. The workflow definition supplies the API order.

*[Click **Failed verification**.]*

Here, the workflow still applies, but the verification rule blocks the account creation step. All the requests and responses in this prototype use fictional data for integration guidance.
