import { useParams } from 'react-router-dom'
import VideoToolPlaceholder from './VideoToolPlaceholder.jsx'
import { getToolPage } from './tools/index.js'

// ---------------------------------------------------------------------------
// One route for every tool in the module.
//
// A tool that has been built renders its workspace; one that has not renders
// the placeholder, generated from the same registry entry that drew its card.
// That keeps App.jsx to a single `/video/:slug` route no matter how many
// phases land, and means a workspace goes live by being added to
// tools/index.js — there is no second place where routing could disagree with
// what exists.
//
// The same shape AdToolRoute uses. Deliberately: two modules that solve the
// same problem two different ways is how a codebase stops being learnable.
// ---------------------------------------------------------------------------

export default function VideoToolRoute() {
  const { slug } = useParams()
  const Workspace = getToolPage(slug)

  return Workspace ? <Workspace /> : <VideoToolPlaceholder />
}
