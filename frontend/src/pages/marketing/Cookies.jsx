import LegalPage from './LegalPage.jsx'
import Seo from '../../components/Seo.jsx'
import { SITE } from '../../config/site'

// ---------------------------------------------------------------------------
// Cookie Policy — a dedicated page rather than a paragraph inside the privacy
// policy. Google's EU user consent policy expects publishers to disclose the
// specific categories of cookies used and how a visitor can change their
// choice, and AdSense reviewers look for this page explicitly.
// ---------------------------------------------------------------------------

const SECTIONS = [
  {
    heading: '1. What Cookies Are',
    body: [
      'Cookies are small text files that a website stores on your device. They are widely used to make websites work, to remember your preferences between visits, and to provide information to the site owner about how the site is being used. Similar technologies such as local storage and pixels work in comparable ways, and this policy covers those too.',
      `This policy explains which cookies ${SITE.name} uses, why we use them, and how you can control them.`,
    ],
  },
  {
    heading: '2. Strictly Necessary Cookies',
    body: [
      'These cookies are required for the Service to function and cannot be switched off in our systems. They are only set in response to actions you take, such as signing in or setting your privacy preferences.',
      'We use them to keep you signed in to your account between page loads, to keep your session secure, and to remember the cookie choice you make on this site. Because these are essential to providing a service you have requested, they are set without requiring consent.',
      'If you block these cookies through your browser, parts of the Service — including signing in — will not work.',
    ],
  },
  {
    heading: '3. Analytics Cookies',
    body: [
      'With your permission, we use analytics cookies to understand how visitors find and use our website, which pages are read, and where people run into difficulty. This helps us improve the product and our content.',
      'We may use Google Analytics for this purpose. Google Analytics sets cookies that collect information such as the pages you visit, how long you spend on them, and the approximate region you are visiting from. We do not use analytics data to identify you personally.',
      'These cookies are only set after you select "Accept all" on our cookie banner. If you decline, no analytics cookies are placed.',
    ],
  },
  {
    heading: '4. Advertising Cookies',
    body: [
      'With your permission, we may display advertising on parts of this website, including articles on our blog. Advertising is provided by Google AdSense.',
      'Google and its partners may use cookies to serve ads based on your prior visits to this website or other websites, and to measure the performance of those ads. Google\'s use of advertising cookies enables it and its partners to serve ads to you based on your visit to our site and other sites on the internet.',
      'You can opt out of personalised advertising by visiting Google\'s Ads Settings at adssettings.google.com. You can also opt out of third-party vendors\' use of cookies for personalised advertising at aboutads.info/choices. Opting out does not remove advertising — it means the advertising you see is less relevant to you.',
      'These cookies are only set after you select "Accept all" on our cookie banner.',
    ],
  },
  {
    heading: '5. Third Parties That May Set Cookies',
    body: [
      'When enabled with your consent, the following third parties may set cookies through this website: Google Analytics (usage measurement), Google AdSense (advertising), and Microsoft Clarity (usage measurement and session insight).',
      'Each of these providers processes data under its own privacy policy, and we recommend reviewing them if you would like to understand their practices in detail. We do not sell your personal information to any of these parties.',
      'When you connect a social media account to the Service, that platform may also set cookies as part of its own authentication flow. Those cookies are governed by that platform\'s policies rather than ours.',
    ],
  },
  {
    heading: '6. How to Change Your Choice',
    body: [
      'You can change your cookie choice at any time by clearing this site\'s data in your browser settings, which will cause our cookie banner to appear again on your next visit so you can make a new selection.',
      'You can also control cookies directly through your browser. Most browsers let you view the cookies stored, delete them individually or entirely, and block cookies from specific sites or all sites. These controls are usually found under Settings, then Privacy or Security.',
      'Blocking all cookies will prevent you from signing in to the Service, because the session cookie is strictly necessary.',
    ],
  },
  {
    heading: '7. Do Not Track',
    body: [
      'Some browsers offer a "Do Not Track" setting. There is currently no agreed industry standard for how sites should respond to these signals, so we do not alter our behaviour based on them. Our cookie banner gives you a direct, explicit choice instead, which we consider clearer than relying on a browser signal.',
    ],
  },
  {
    heading: '8. Changes to This Policy',
    body: [
      'We may update this Cookie Policy as our use of cookies changes or as legal requirements evolve. When we make material changes, we will update the date shown at the top of this page and, where appropriate, ask for your consent again.',
      `If you have questions about this policy or how we use cookies, please contact us at ${SITE.supportEmail}.`,
    ],
  },
]

export default function Cookies() {
  return (
    <>
      <Seo />
      <LegalPage title="Cookie Policy" updated="August 3, 2026" sections={SECTIONS} />
    </>
  )
}
