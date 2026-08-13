/**
 * Route table.
 *
 * Two durable addresses: the title screen, and a room. `/r/:code` is the
 * invite link — it is the only URL a player ever shares, and it works whether
 * the room is still at the campfire or already in the forest.
 *
 * `RoomScreen` tears its socket down on unmount and `ArenaScreen` disposes its
 * game, so navigating between these is safe in both directions.
 */

import { createBrowserRouter } from 'react-router';
import { HomeScreen } from '../screens/HomeScreen';
import { RoomScreen } from '../screens/RoomScreen';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: HomeScreen,
  },
  {
    path: '/r/:code',
    Component: RoomScreen,
  },
]);
