IPPS — PUBLIC DIGITAL INTEGRITY EVIDENCE REPORT
============================================================

Report generated (UTC): 2026-11-18T09:47:12.770611+00:00
System: IPPS
Hash algorithm: SHA-256
Digital signature algorithm: Ed25519
Number of registered archives: 4

1. PURPOSE
------------------------------------------------------------
This report documents cryptographic registration and integrity
verification of four software project archives.

2. REGISTERED PROJECTS AND CRYPTOGRAPHIC RECORDS
------------------------------------------------------------
Record: 1
Project: LEGEND JUDGE v8.2
Archive: LEGEND_JUDGE_v8_2.zip
Size: 52611 bytes
SHA-256: cc4556ad2468b6dfd2cd79023b15d27ef6c3a6095b88b9975968174a0f1bfeef
Registration time: 2026-11-18T09:15:23.126675+00:00
Previous chain: 0000000000000000000000000000000000000000000000000000000000000000
Chain hash: 8881ef38416325c5c67d30b57c13cb3a7f2ed5d70c224900c23275bb621e9908
Ed25519 signature: wKereEYSrEq22r3ZHqJ6xBUIOXCxhXZnxJhBoEQTTTbV+xPhFyAaDdi8HAX1fWMtBfR87ex7xMp41UCfzuIlBQ==
-----------------------------------------------------------------
Record: 2
Project: Terminal Legend v18
Archive: Terminal-Legend-v18.zip
Size: 146527 bytes
SHA-256: 5e0a1ac1bba12251bd1775075ad154972a0b501ba7cbd1c860ffdc287d8c91bc
Registration time: 2026-11-18T09:15:23.232893+00:00
Previous chain: 8881ef38416325c5c67d30b57c13cb3a7f2ed5d70c224900c23275bb621e9908
Chain hash: c73d79e2459f336dc53659f4132cbd15c7de116fe1b55a4662ad8c920c80f8e3
Ed25519 signature: 3FiBWnZPz8AzLx81R94Q0UT44PIuzazXFTOAW30+hCBKdFhlFqKK0FAEKJchtTBEQcBoshjB4Tt7/Gt+/8/aBQ==
-----------------------------------------------------------------
Record: 3
Project: LEGEND CTF v187
Archive: legend_ctf_v187.zip
Size: 2783809 bytes
SHA-256: 38197d201447ede9720b5937c243569be474fd48f309516b46eb6729e6fb755d
Registration time: 2026-11-18T09:15:23.340388+00:00
Previous chain: c73d79e2459f336dc53659f4132cbd15c7de116fe1b55a4662ad8c920c80f8e3
Chain hash: 7d531151683f6819b5075f1ee4f55d9243c6226b12cd2647c014121e1b8f214e
Ed25519 signature: UwJyZvZsG0iM17gQwF0LmGqz0UHBqPFkTLl9Jwud+SX8gedvVW1YkAYL/I37QnUznKKG+WbCsyA+yDkhSWQSAw==
-----------------------------------------------------------------
Record: 4
Project: Vulnerability Range v15
Archive: vuln-range-18-v15.zip
Size: 88448 bytes
SHA-256: 221d9d0cd3adc60a339010c43d3d90ad878f12f070978bf33e3c67c9c08a7c14
Registration time: 2026-11-18T09:15:24.532225+00:00
Previous chain: 7d531151683f6819b5075f1ee4f55d9243c6226b12cd2647c014121e1b8f214e
Chain hash: 0325c0889bcce5375ac057d5889df4527a2101e94756d7ea42b8cbface7efe09
Ed25519 signature: uuM1Q4syZoaDzHnDtI3/66FEvbM7KXTzWnD+ptW9S6r423/eXh96ydaldBBTtk4Ja+rKrWRvki9/V1QPyEOrAA==
-----------------------------------------------------------------

3. FINAL HASH CHAIN
------------------------------------------------------------
0325c0889bcce5375ac057d5889df4527a2101e94756d7ea42b8cbface7efe09

4. PUBLIC KEY IDENTIFICATION
------------------------------------------------------------
Algorithm: Ed25519
Public key SHA-256 fingerprint:
ccb3a123389806b8db2e38e88a0d99a833062c13d125c98793ee403717ed6d0e

Public key:
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAw4oNsoOCUAaVz8smwDP1+bpBAQbgJWPAi1gGMnZ9UQQ=
-----END PUBLIC KEY-----

5. INDEPENDENT VERIFICATION
------------------------------------------------------------
[OK] Public key fingerprint
[OK] 1/4 LEGEND_JUDGE_v8_2.zip: hash, chain, signature
[OK] 2/4 Terminal-Legend-v18.zip: hash, chain, signature
[OK] 3/4 legend_ctf_v187.zip: hash, chain, signature
[OK] 4/4 vuln-range-18-v15.zip: hash, chain, signature

SUCCESS: All public evidence checks passed.
FINAL CHAIN: 0325c0889bcce5375ac057d5889df4527a2101e94756d7ea42b8cbface7efe09
PUBLIC KEY SHA256: ccb3a123389806b8db2e38e88a0d99a833062c13d125c98793ee403717ed6d0e


6. TAMPERING TEST
------------------------------------------------------------
A modified copy of a manifest was tested by changing a project label.
The independent verifier rejected the modified manifest.
Previously observed result: PASS.

7. VERIFICATION SCOPE
------------------------------------------------------------
The verification checks archive sizes, SHA-256 fingerprints,
record ordering, previous-chain relationships, recomputed chain
hashes, public-key fingerprint, and Ed25519 signatures.

8. LIMITATIONS
------------------------------------------------------------
This report does not independently prove legal identity, legal
ownership, original authorship, or original creation dates.
Local timestamps are not independent trusted timestamps.

9. PUBLIC EVIDENCE FILES
------------------------------------------------------------
public-manifest.json
public.pem
verify_public.py
VERIFICATION-RESULTS.txt

The private key is not included.

============================================================
END OF PUBLIC REPORT
============================================================
