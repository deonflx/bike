from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission for BikeTrip:
    - Safe methods (GET, HEAD, OPTIONS) are allowed to all users.
    - Write/Delete methods (POST, PUT, PATCH, DELETE) require authentication
      and the object's owner must match request.user (or user is staff).
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        # If the trip has no owner assigned, only staff can modify/delete it
        if not obj.user:
            return bool(request.user.is_staff)
        return bool(obj.user == request.user or request.user.is_staff)


class IsSessionOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission for TripSession:
    - Safe methods (GET, HEAD, OPTIONS) are allowed to all users so convoy companions
      and spectators can view live telemetry on the map.
    - Updates (PATCH GPS coordinates, ending session, DELETE) are strictly restricted
      to the owner of the trip associated with this session.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        trip_user = obj.bike_trip.user if obj.bike_trip else None
        if not trip_user:
            return bool(request.user.is_staff)
        return bool(trip_user == request.user or request.user.is_staff)


class IsConnectionParticipant(permissions.BasePermission):
    """
    Permission for ConnectionRequest:
    - Only authenticated users can access connection requests.
    - Users can only view, respond to, or delete connection requests where they
      are either the sender or the receiver.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(
            obj.sender == request.user or
            obj.receiver == request.user or
            request.user.is_staff
        )
