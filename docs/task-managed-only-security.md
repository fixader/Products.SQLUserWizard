# Oppgave: Forenkle SQLUserWizard og rette sikkerhetshull

Dette er det levende oppgavedokumentet for denne tasken. Oppdater status,
beslutninger, verifikasjon og gjenstående arbeid når endringer blir gjort.

Opprettet: 2026-09-24
Sist oppdatert: 2026-09-25
Status: Fersk installasjon og avgrenset oppgradering er verifisert på labens PostgreSQL over HTTP og ekte omstart. Laben er gjenopprettet; ingen generell utrulling.

### Nåstatus for kontrolllesing

Forenkling, sikkerhetstiltak og oppgraderingsvei er implementert lokalt.
126 tester passerer, også fra bygget kildepakke. Wheel og kildepakke passerer
twine-kontroll. Install / Repair avviser nå overskriving av avvikende SQL før
databasearbeid. Gjenstår: direkte Lavaart/Lavaart_pg-verifikasjon, sluttgjennomgang
og opprydding i byggemetadata før endelig pakking. Ingen PyPI-publisering er gjort.
Dokumentasjonen publiseres separat for brukerens kontrolllesing; den beskriver
arbeidskandidaten, ikke en allerede publisert versjon. Sjekklistene og
statuspunktene nedenfor er den opprinnelige planen og kronologisk arbeidshistorikk.

## Mål og avgrensning

SQLUserWizard skal opprette og administrere sitt eget SQL-brukerskjema på
alle støttede databaser. Wizarden skal ikke koble autentisering til en
eksisterende SQL-brukerbase eller migrere/overtake dens tabeller. Brukeren
står selv for eventuell senere import av egne data.

Arvede Zope-brukere, synkronisering til fallback-brukere og nødtilgang
beholdes. Disse er ikke omfattet av fjerningen av SQL-migrering.

## Arbeid og akseptansekriterier

### 1. Fjern eksisterende SQL-brukerbase og migrering

- [ ] Fjern `auth_only` og dialekter for eksisterende brukerskjemaer.
- [ ] Fjern migrerings-/overtakelseslogikk og genererte migreringsmetoder.
- [ ] Fjern tilhørende skjermvalg og hjelpetekster.
- [ ] Oppdater tester og dokumentasjon slik at de beskriver den nye modellen.

Akseptanse: En ny installasjon tilbyr ingen kobling til gamle SQL-brukertabeller,
ingen migreringshandling og ingen generert migrerings-SQL.

### 2. Opprett produktets egne tabeller

- [ ] Bruk samme installasjonsprinsipp for alle støttede databaser.
- [ ] Tilby valgbare navn, eksempelvis `pas_users` og `pas_roles`.
- [ ] Behold separate tabeller for brukere, rollekatalog, rolletildelinger og profiler.
- [ ] Valider tabellnavn og stopp ved kollisjon med fremmede tabeller.
- [ ] Behold gjentakbar installasjon/reparasjon av wizardens egne tabeller.
- [ ] Håndter gamle innstillinger eksplisitt uten automatisk overtakelse av tabeller.

Akseptanse: Wizarden oppretter eget skjema med de valgte navnene. Gjentatt
reparasjon bevarer egne data. Fremmede tabeller endres ikke.

### 3. Behold arvede brukere og fallback

- [ ] Behold støtte for arvede Zope-brukere og lokal fallback-/nødtilgang.
- [ ] Verifiser at forenklingen ikke ødelegger denne tilgangen.

### 4. Rett sikkerhetshullene

- [ ] Hindre autentisering som omgår aktivert 2FA.
- [ ] Sikre at cookie-flyten kan skille fullført 2FA fra kun godkjent passord.
- [ ] Sikre påkrevd 2FA-innmelding før ordinær tilgang gis.
- [ ] Krev POST og CSRF-beskyttelse for handlinger som endrer data eller oppsett.
- [ ] Valider redirect-adresser etter innlogging.
- [ ] Legg til regresjonstester som demonstrerer at hullene er lukket.

Akseptanse: Manglende/ugyldig 2FA gir ikke ordinær tilgang; GET og forespørsler
uten gyldig CSRF-beskyttelse kan ikke utføre endringer; innlogging kan ikke
videresende til en vilkårlig ekstern adresse.

### 5. Struktur, dokumentasjon og verifikasjon

- [ ] Rydd struktur der det støtter forenklingen og sikkerhetsrettingene.
- [ ] Bevar nødvendig kompatibilitet med lagrede Zope-objekter ved kodeflytting.
- [ ] Oppdater installasjonsbeskrivelse, produktstatus og endringslogg.
- [ ] Kjør relevant testsuite og registrer resultatene her.
- [ ] Verifiser installasjon, reparasjon, innlogging, 2FA og fallback i tilgjengelige
  Zope-/databasemiljøer. Skill lokale tester fra faktisk integrasjonsverifikasjon.

## Utgangspunkt

- Repository: https://github.com/fixader/Products.SQLUserWizard
- Lokal arbeidskopi: `C:\Users\rf\Documents\Products.SQLUserWizard`
- Undersøkt gren/commit: `main`, `8944411`.
- Pakkeversjon: `0.1.0a2`.
- Før endringer: 70 tester passerer på Python 3.13.0.
- Tidligere dokumenterte Zope-/databaselabtester er ikke gjentatt i denne tasken.

Funn fra første gjennomgang:

- Det genererte autentiseringsskriptet godtok i en lokal reproduksjon passord
  uten OTP for en bruker med aktivert 2FA når skjemafelt manglet. Hele PAS-flyten
  må verifiseres ved retting.
- En lokal reproduksjon viste at GET kunne nå administratorens sletteoperasjon.
- De undersøkte endringsmetodene manglet eksplisitt CSRF-kontroll.
- Innloggingskontrolleren brukte `came_from` direkte som redirect-adresse.
- Store moduler blander installasjon, HTML, SQL og autentisering.

## Beslutninger og åpne implementasjonsvalg

Avklart med brukeren:

- Støtte for eksisterende SQL-brukerbaser og migrering skal fjernes.
- Wizarden skal selv opprette brukertabeller og rolletabeller med valgbare navn.
- Arvede brukere skal beholdes.
- Sikkerhetshullene skal rettes.
- Dette dokumentet skal holdes oppdatert mens arbeidet pågår.

Avklares i implementasjonen og dokumenteres her:

- Endelige standardnavn for tabellene; dagens rollekatalog heter `pas_roles_catalog`.
- Hvordan eierskap til eksisterende wizard-tabeller verifiseres ved reparasjon.
- Hvordan tidligere installerte migreringsobjekter og gamle `auth_only`-oppsett
  håndteres uten utilsiktede databaseendringer.
- Teknisk løsning for 2FA-bevis, cookies og begrenset innmeldingstilgang.
- Hvilke Zope-/databasemiljøer som er tilgjengelige for integrasjonstesting.

## Fremdriftslogg

| Dato | Endring | Verifikasjon / gjenstående |
| --- | --- | --- |
| 2026-09-24 | Første statusgjennomgang og lokal kloning. | 70 tester passerte. To sikkerhetsproblemer ble reprodusert lokalt. Ingen produksjonsendringer. |
| 2026-09-24 | Oppgavebeskrivelse lagret etter brukerens ønske. | Kun dokumentasjon er endret. Implementering avventer videre arbeid. |

### Pågående arbeid

- Migreringsgeneratorer og eksisterende-skjema-valg er fjernet.
- Ny standard for rollekatalog er `pas_roles`; lagrede tabellnavn beholdes ved reparasjon.
- Tabellnavn og manifest kontrolleres før installasjonen gjør endringer.
- Serverlagrede sesjoner og separat innmeldingstilgang erstatter passordcookies.
- POST/CSRF og lokale redirect-adresser kobles til skjermflytene.
- Direkte publisering av genererte SQL-metoder stenges; betrodd Python-kode kaller dem internt.
- Dette er en mellomtilstand. Tester og integrasjonsverifikasjon gjenstår.

### Kontrollpunkt etter ønske om lavere forbruk

- Kjerneendringene hadde 114 beståtte tester på Python 3.13 / Zope 6.1 /
  PAS 4.1 / ZSQLMethods 5.1 før kompatibilitetsblokken startet.
- Testene inkluderer faktisk Zope/PAS i prosess og en midlertidig SQLite-database.
  Andre levende databaseinstanser og Zope 5 er ikke testet på nytt.
- Innlogging, begrenset 2FA-innmelding, POST/CSRF, redirect, beskyttede SQL-metoder,
  fallback, tabellkollisjon og reparasjon har lokale regresjonstester.
- Brukeren presiserte at ferdig migrerte eldre installasjoner må kunne oppgraderes
  uten å kjøre datamigrering igjen eller miste tabellnavn, brukere og roller.
- `upgrade.py` og en oppstartshook er skrevet som pågående arbeid. Denne nye
  oppgraderingsflyten er ENNÅ IKKE testet fra faktisk gammel versjon. Gjennomgå
  oppstartsfeilhåndtering, tilpassede maler og innlesing av lagrede standardverdier
  før den kan brukes. Dagens kode kan stoppe oppstart ved en oppgraderingsfeil.
- `docs/upgrade.md` beskriver fortsatt den tidligere planen om manuell reparasjon;
  den må oppdateres når kompatibilitetsflyten er ferdig bestemt og verifisert.
- Ingen endringer er pushet, publisert eller satt i drift. Arbeidet er lokalt og
  ikke committet. Kontrollpunktet er ikke en ferdig utgivelse.

Neste avgrensede blokk:

1. Gjennomgå oppstartshooken og sikre at en enkelt gammel/tilpasset installasjon
   ikke velter resten av Zope ved oppgradering.
2. Lag en oppgraderingstest med objekter generert av faktisk 0.1.0a2, inkludert en
   ferdig migrert installasjon med egne tabellnavn. Kontroller at SQL-data ikke røres.
3. Oppdater oppgraderingsdokumentasjon og rapporter resultat før mer arbeid.

Arbeidsform videre: mindre blokker, hyppigere status og et tydelig stopp før
neste større blokk for å begrense forbruket.

### Oppgraderingsblokk fullført lokalt

- Faktisk kildekode fra commit `8944411` (0.1.0a2) er frosset som testgrunnlag.
  Den gamle installatøren kjøres i egen prosess; dens eksporterte ZODB-objekter
  lastes under ny kode og oppgraderes.
- Verifisert ferdig migrert tabelloppsett: `pas_users_migrated`,
  `pas_roles_catalog`, `pas_user_roles_migrated`, `pas_user_profiles`.
- Oppgraderingen kjører ingen SQL-spørringer og endrer ikke SQL-data. Eksisterende
  passord, 2FA, rolledata og fallback-konto virker etterpå. Gamle standardverdier
  på wizard-objekter hentes fra manifestet fremfor nye klassestandarder.
- Oppstartshook er registrert ved normal produktinitialisering. Fullført
  oppgraderingsrevisjon hoppes over ved senere oppstart.
- Feil i én mappe ruller tilbake den mappens delvise endringer, sperrer dens
  SQL-autentisering og viser feilstatus. Andre mapper gjennomgås videre;
  ZODB fallback beholdes. En rettet installasjon kan oppgraderes på nytt.
- Vanlige tilpassede DTML-innloggingsskjema får CSRF-felt uten at layout erstattes.
  Ukjente skjemavarianter krever gjennomgang og behandles som oppgraderingsfeil.
- Samlet testresultat: **118 bestått**, ren `git diff --check`.
- Oppgraderingsdokumentasjonen er oppdatert. Testmiljøet er fortsatt Zope 6.1,
  Python 3.13 og midlertidig SQLite; full serveroppstart og Zope 5 / andre levende
  databaseinstanser er ikke verifisert her.
- Ingen push, commit eller endringer i kjørende installasjoner. Vi stopper ved
  dette kontrollpunktet for å holde forbruket avgrenset.

Denne oppføringen erstatter den tidligere statusen om at kompatibilitetsblokken
ikke var testet. Historiske fremdriftsnotater over er beholdt som arbeidslogg.

### Labkartlegging 2026-09-25 – kun lesing

- Bekreftet `zopedatest` på `192.168.0.12`, Zope på port 8081.
- Python 3.14.4, Zope 6.1, PAS 4.1, ZSQLMethods 5.1.
- SQLUserWizard rapporterer 0.1.0 og er editable-installert fra
  `/home/codex/openodbcda-lab/Products.SQLUserWizard`. Koden inneholder
  cookie-dobbeltkodingsrettingen og brukeropplisting. Versjonsetiketten alene
  er dermed ikke tilstrekkelig til å identifisere kodens tilstand.
- `/PASProductLab`: managed, lokal PostgreSQL `openodbc_test`, vanlige `pas_*`-tabeller.
- `/PAS2FALab`: managed, samme lokale PostgreSQL, egne `pas2fa_*`-tabeller.
- `/PASSmoke_sqlite` og `/PASSmoke_mysql`: egne tabeller på lokale databaser.
- `/PASSmoke_pg`: PostgreSQL på 192.168.0.11. `/PASSmoke_mssql` peker på
  lokal port 11433, som ikke var i listen over lyttende porter. Tilkobling er ikke testet.
- `/PASProductLab_existing_pg` og `/PASProductLab_existing_oracle` er fortsatt
  auth_only, og skal ikke tolkes som ferdig migrerte installasjoner.
- `/PASProductLab_pg_remote` har et gammelt manifest UTEN mode-felt; dagens
  oppgraderingskode vil hoppe over dette. Krever eksplisitt kompatibilitetstest.
- `/Lavaart` har migrerte tabellnavn og Oracle-tilkobling.
- VIKTIG: `/Lavaart_pg` har manifest OG wizard satt til oracle11g, mens dens
  aktive `VolumOrdre`-adapter peker til PostgreSQL-databasen `lavaart` på
  192.168.0.11. Manifestet er ikke en pålitelig fasit for å regenerere SQL her.
  Dagens automatiske oppgradering må ikke kjøres ukritisk mot denne installasjonen.
- ZODB ble åpnet med FileStorage(read_only=True). Ingen tjenester ble startet
  eller stoppet, ingen pakker ble installert, og ingen SQL-spørringer ble kjørt.
- Neste anbefalte testmål er en isolert kopi av PASProductLab/PAS2FALab og en
  fersk testmappe. Før noen pakkeoppdatering på den delte instansen må
  oppgraderingen håndtere manglende/gammelt manifest og avvik mellom manifest,
  adapter og faktisk SQL, eller avgrenses til eksplisitt valgte testmapper.

Labfunnene over avdekker nye kompatibilitetstilfeller som ikke dekkes av den
allerede beståtte 0.1.0a2-testen. Ingen utrulling er godkjent eller utført i denne
kartleggingsblokken.

### Direkte labtest fullført 2026-09-25

- Brukeren godkjente direkte labtesting med backup og avgrensning til utvalgte mapper.
- Backup: `/home/codex/openodbcda-lab/backups/sqluw-upgrade-20260925T052203Z`.
- Tjenesten er `zopedatest-zope61.service` (systemd, Restart=always).
- Ny miljøvariabel `SQLUSERWIZARD_UPGRADE_PATHS` avgrenser automatisk oppgradering
  til eksakte fysiske mappestier. Labtesten valgte PASProductLab og PAS2FALab.
- Ekte oppstart oppgraderte begge mappene. Kontrollsummer og radantall for åtte
  eksisterende SQL-tabeller var uendret både etter oppgradering og etter testopprydding.
- HTTP-tester besto for innlogging/roller, avvist manglende OTP, korrekt 2FA,
  innmelding uten ordinær tilgang, aktivering, utlogging, CSRF og GET-sperrer.
- Fersk PostgreSQL-installasjon gjennom HTTP/ZMI besto, inkludert opprettelse av
  wizard, tabeller, første bruker, profilskriving og reparasjon.
- Funn/retting: PAS2FALab bruker fortsatt login_name-kolonnen. Runtime-oppgradering
  bevarer nå eksisterende SQL-kode i stedet for å generere den fra nye maler.
- Funn/retting: CSRF-token for ZMI-produktfabrikken må knyttes til den persistente
  foreldremappen. Dette er rettet og regresjonstestet.
- Sluttresultat lokalt: 120 tester passerer; git diff --check er ren.
- Midlertidige SQL-brukere og fire ferske testtabeller er fjernet. Gammel kode og
  ZODB er gjenopprettet fra backup, inkludert fjerning av midlertidig testadministrator
  og mapper. Midlertidig systemd-miljøinnstilling er fjernet. Tjenesten er aktiv og
  svarte HTTP 200 etter gjenoppretting.
- Den testede kandidatkoden er bevart i backupens `candidate-tested`-mappe.
  Ingen Git-push eller commit er gjort.

Gjenstående særtilfeller før generell utrulling: manifest uten mode-felt,
retirerte auth_only-installasjoner og direkte test av Lavaart/Lavaart_pg. Zope 5
og øvrige levende databasemotorer er heller ikke testet i denne blokken.

### Kompatibilitetsblokk: eldre manifest og lokal SQL

- Manifest uten mode blir nå rapportert som oppgraderingsavvik; gammel SQL-auth
  deaktiveres gjennom eksisterende feilisolering, mens ZODB-fallback beholdes.
  Automatisk konvertering av denne tidlige varianten er fortsatt uavklart.
- Managed-installasjoner må ha SQL-metodene som de nye kontrollerne trenger,
  inkludert update_2fa, før runtime-oppgraderingen starter.
- Regresjonstest bekrefter innlogging med feil dialect i manifest og lokalt
  tilpasset SQL. SQL-kode, argumenter og tilkoblings-ID bevares.
- Neste konkrete kodepunkt: sikre Install / Repair mot overskriving av lokal
  SQL ved utdatert manifest. Runtime-oppgraderingen bevarer dette allerede.
- Ingen endringer på labmaskinen i denne blokken.
- Verifisert: 123 tester passerer; git diff --check uten feil.

### Avklart støttegrense etter brukerens tilbakemelding

- Automatisk konvertering av de tidligste eksperimentelle laboppsettene tas ut
  av gjenstående leveranse. De skal avvises og kreve særskilte manuelle tiltak.
- Eldste verifiserte kildeversjon er 0.1.0a2, commit 8944411. Denne skriver selv
  version=0.1.0 i manifestet; et rent numerisk versjonsskille er derfor upålitelig.
- Teknisk grense er eksplisitt managed-manifest, gyldig tabellmapping og de
  nødvendige SQL-metodene, inkludert update_2fa. Eksisterende kontroller avviser
  manglende mode/metoder og beholder fallback ved oppgraderingsfeil.
- docs/upgrade.md beskriver støttegrensen og manuell håndtering. Tidligere
  punkter om automatisk støtte for disse gamle testoppsettene er erstattet av
  denne avklaringen. Ferdig migrerte managed-installasjoner forblir innenfor.
- Ingen kodeendring eller ny labendring i denne dokumentasjonsblokken.
- Brukeren presiserte at tiltak for gamle testoppsett kan være avinstallering
  og nyinstallering. Dette er dokumentert som normal løsning for slike oppsett;
  egen konverteringskode er ikke påkrevd. Reinstallering av Python-pakken alene
  fjerner ikke gamle ZODB-objekter/tabeller. Ingen avinstallering er utført.
