import { useParams } from 'react-router-dom'
import AdToolPlaceholder from './AdToolPlaceholder.jsx'
import { getToolPage } from './tools/index.js'

// ---------------------------------------------------------------------------
// One route for every tool in the module.
//
// A tool that has been built renders its workspace; one that has not renders
// the placeholder, which is generated from the same registry entry. That keeps
// App.jsx to a single `/ads/:slug` route no matter how many phases land, and
// means a workspace goes live by being added to tools/index.js — there is no
// second place where routing could disagree with what exists.
// ---------------------------------------------------------------------------

export default function AdToolRoute() {
  const { slug } = useParams()
  const Workspace = getToolPage(slug)

  return Workspace ? <Workspace /> : <AdToolPlaceholder />
}
